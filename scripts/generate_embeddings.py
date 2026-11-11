#!/usr/bin/env python3
"""Gera embeddings locais para nós :Trecho e garante o índice vetorial ``trecho_embedding_vector``.

Cada trecho é codificado inteiro: o texto é dividido em janelas de tokens com sobreposição e os
vetores das janelas são combinados num único vetor normalizado de 384 dimensões (estratégia em
``app/services/embeddings.py``, a mesma usada para codificar as perguntas). ``Trecho.texto`` não é
alterado e nenhum nó novo é criado.

Propriedades gravadas no ``Trecho``: ``embedding``, ``embedding_model``,
``embedding_pipeline_version`` (identifica a estratégia) e ``embedding_windows``.

Processa os trechos sem embedding, com outro modelo ou com versão de estratégia diferente da atual
(``--force`` reprocessa todos). Requer Neo4j ativo, schema de dev3, Trecho carregados por dev4 e
``.env`` local.

Uso:
    python scripts/generate_embeddings.py --batch-size 32
    python scripts/generate_embeddings.py --dry-run      # só conta pendentes por motivo, não grava
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.embeddings import (  # noqa: E402
    CREATE_VECTOR_INDEX,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_PIPELINE_VERSION,
    MODEL_NAME,
    SHOW_VECTOR_INDEX,
    VECTOR_INDEX,
    vector_index_problems,
)

NORM_TOLERANCE = 1e-3

# O motivo explica por que o trecho será (re)processado; ordem de prioridade dos CASE.
SELECT_PENDING = """
MATCH (t:Trecho)
WITH t, CASE
  WHEN $force THEN 'forcado'
  WHEN t.embedding IS NULL THEN 'sem_embedding'
  WHEN t.embedding_model IS NULL OR t.embedding_model <> $model THEN 'modelo_diferente'
  WHEN t.embedding_pipeline_version IS NULL OR t.embedding_pipeline_version <> $version THEN 'versao_antiga'
END AS motivo
WHERE motivo IS NOT NULL
RETURN t.trecho_id AS trecho_id, t.texto AS texto, motivo
ORDER BY trecho_id
"""

WRITE_EMBEDDINGS = """
UNWIND $rows AS row
MATCH (t:Trecho {trecho_id: row.trecho_id})
SET t.embedding = row.embedding,
    t.embedding_model = $model,
    t.embedding_pipeline_version = $version,
    t.embedding_windows = row.windows
RETURN count(t) AS atualizados
"""

VERIFY = """
MATCH (t:Trecho)
WITH t, CASE WHEN t.embedding IS NULL THEN null
             ELSE sqrt(reduce(s = 0.0, x IN t.embedding | s + x * x)) END AS norma
RETURN count(t) AS total,
       count(t.embedding) AS com_embedding,
       min(size(t.embedding)) AS dimensao_min,
       max(size(t.embedding)) AS dimensao_max,
       min(norma) AS norma_min,
       max(norma) AS norma_max,
       collect(DISTINCT t.embedding_model) AS modelos,
       collect(DISTINCT t.embedding_pipeline_version) AS versoes,
       count(CASE WHEN t.embedding_model = $model AND t.embedding_pipeline_version = $version THEN 1 END)
         AS na_versao_atual,
       sum(t.embedding_windows) AS janelas,
       max(t.embedding_windows) AS janelas_max
"""


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' não é um número inteiro válido.")
    if number < 1:
        raise argparse.ArgumentTypeError(f"o valor deve ser maior ou igual a 1 (recebido: {value}).")
    return number


def ensure_vector_index(session: Any) -> List[str]:
    """Cria o índice se não existir e confere nome, rótulo, propriedade, dimensão e similaridade."""
    session.run(CREATE_VECTOR_INDEX).consume()
    row = session.run(SHOW_VECTOR_INDEX, name=VECTOR_INDEX).single()
    return vector_index_problems(row.data() if row else None)


def verification_problems(check: Dict[str, Any], complete_run: bool) -> List[str]:
    """Confere no banco o que o índice e o serviço esperam dos vetores gravados."""
    problems = []
    if check["com_embedding"] and (check["dimensao_min"] != EMBEDDING_DIMENSIONS
                                   or check["dimensao_max"] != EMBEDDING_DIMENSIONS):
        problems.append(f"há embeddings fora de {EMBEDDING_DIMENSIONS} dimensões")
    if check["com_embedding"] and not (abs(check["norma_min"] - 1) <= NORM_TOLERANCE
                                       and abs(check["norma_max"] - 1) <= NORM_TOLERANCE):
        problems.append(f"há embeddings não normalizados (norma {check['norma_min']}..{check['norma_max']})")
    if complete_run and check["na_versao_atual"] != check["total"]:
        problems.append(f"{check['total'] - check['na_versao_atual']} Trecho fora da versão atual da estratégia")
    return problems


def generate(driver: Any, args: argparse.Namespace, database: str) -> int:
    with driver.session(database=database) as session:
        if not args.dry_run:
            problems = ensure_vector_index(session)
            if problems:
                for problem in problems:
                    print(f"Erro: {problem}", file=sys.stderr)
                print("Alinhe o índice com dev3 antes de gravar embeddings.", file=sys.stderr)
                return 1
            print(f"Índice vetorial {VECTOR_INDEX} conferido ({EMBEDDING_DIMENSIONS} dimensões, cosine).")
        records = session.run(SELECT_PENDING, force=args.force, model=MODEL_NAME,
                              version=EMBEDDING_PIPELINE_VERSION).data()

    if args.limit:
        records = records[: args.limit]
    pending = [r for r in records if (r["texto"] or "").strip()]
    reasons = Counter(r["motivo"] for r in records)
    print(f"Versão da estratégia: {EMBEDDING_PIPELINE_VERSION}")
    print(f"Trechos pendentes: {len(records)} {dict(sorted(reasons.items()))} "
          f"(sem texto, ignorados: {len(records) - len(pending)})")
    if args.dry_run or not pending:
        if args.dry_run:
            print("Dry-run: nenhuma escrita no Neo4j.")
        return 0

    from app.services.embeddings import SentenceEncoder

    encoder = SentenceEncoder()
    plans = {r["trecho_id"]: encoder.window_plan(r["texto"]) for r in pending}
    windows = [len(p["janelas"]) for p in plans.values()]
    missing = sum(p["tokens_nao_representados"] for p in plans.values())
    print(f"Modelo carregado: {MODEL_NAME} | limite padrão do modelo: {encoder.default_max_seq_length} | "
          f"janela: {encoder.window_tokens} tokens + {encoder.special_tokens} especiais = "
          f"{encoder.max_seq_length} | sobreposição: {encoder.overlap}")
    print(f"Cobertura: {sum(1 for p in plans.values() if p['tokens_nao_representados'] == 0)}/{len(plans)} "
          f"trechos representados integralmente | {sum(windows)} janelas (máx. {max(windows)} por trecho; "
          f"{sum(1 for w in windows if w > 1)} trechos com mais de uma) | tokens não representados: {missing}")
    if missing:
        print("Erro: a segmentação deixou tokens sem representação.", file=sys.stderr)
        return 1

    total = 0
    with driver.session(database=database) as session:
        for start in range(0, len(pending), args.batch_size):
            batch = pending[start:start + args.batch_size]
            vectors = encoder.encode([r["texto"] for r in batch], batch_size=args.batch_size)
            rows: List[Dict[str, Any]] = [
                {"trecho_id": r["trecho_id"], "embedding": v, "windows": len(plans[r["trecho_id"]]["janelas"])}
                for r, v in zip(batch, vectors)
            ]
            updated = session.execute_write(
                lambda tx: tx.run(WRITE_EMBEDDINGS, rows=rows, model=MODEL_NAME,
                                  version=encoder.pipeline_version).single()["atualizados"]
            )
            total += updated
            print(f"Embeddings gravados: {total}/{len(pending)}")

        session.run("CALL db.awaitIndex($name, 300)", name=VECTOR_INDEX).consume()
        check = session.run(VERIFY, model=MODEL_NAME, version=EMBEDDING_PIPELINE_VERSION).single().data()

    print(
        f"Concluído. trechos atualizados={total}; Trecho com embedding={check['com_embedding']}/{check['total']}; "
        f"na versão atual={check['na_versao_atual']}/{check['total']}; "
        f"dimensão min/max={check['dimensao_min']}/{check['dimensao_max']}; "
        f"norma min/max={check['norma_min']:.6f}/{check['norma_max']:.6f}; "
        f"janelas={check['janelas']} (máx. {check['janelas_max']}); versões={check['versoes']}"
    )
    problems = verification_problems(check, complete_run=not args.limit)
    for problem in problems:
        print(f"Erro: {problem}.", file=sys.stderr)
    return 1 if problems else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Gera embeddings de Trecho e garante o índice vetorial.")
    parser.add_argument("--batch-size", type=positive_int, default=32)
    parser.add_argument("--limit", type=positive_int, default=None, help="Processa no máximo N trechos pendentes")
    parser.add_argument("--force", action="store_true", help="Reprocessa também trechos já atualizados")
    parser.add_argument("--database", default=None, help="Banco Neo4j (padrão: NEO4J_DATABASE ou neo4j)")
    parser.add_argument("--dry-run", action="store_true", help="Só conta pendentes; não cria índice nem grava")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    from neo4j import GraphDatabase
    from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable

    load_dotenv(ROOT / ".env")
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    database = args.database or os.getenv("NEO4J_DATABASE", "neo4j")
    if not password or password == "change_this_password_before_starting":
        print("Configure NEO4J_PASSWORD no .env local antes de executar.", file=sys.stderr)
        return 2

    try:
        with GraphDatabase.driver(uri, auth=(user, password)) as driver:
            driver.verify_connectivity()
            return generate(driver, args, database)
    except AuthError:
        print("Falha de autenticação. Confira NEO4J_USER e NEO4J_PASSWORD no .env.", file=sys.stderr)
    except ServiceUnavailable:
        print("Neo4j não está acessível. Inicie o Docker Compose e confira a porta 7687.", file=sys.stderr)
    except Neo4jError as exc:
        print(f"Erro retornado pelo Neo4j: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
