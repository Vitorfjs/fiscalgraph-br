#!/usr/bin/env python3
"""Gera embeddings locais para nós :Trecho e garante o índice vetorial ``trecho_embedding_vector``.

Processa somente trechos sem embedding ou cujo ``embedding_model`` difere do modelo configurado
(``--force`` reprocessa todos). Grava ``embedding`` (384 floats normalizados) e
``embedding_model``. Modelo, dimensão e índice vêm de ``app/services/embeddings.py``, os mesmos
usados pelo serviço de recuperação.

Requer Neo4j ativo, schema de dev3 aplicado, Trecho carregados por dev4 e ``.env`` local.

Uso:
    python scripts/generate_embeddings.py --batch-size 32
    python scripts/generate_embeddings.py --dry-run      # só conta pendentes, não grava
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.embeddings import (  # noqa: E402
    CREATE_VECTOR_INDEX,
    EMBEDDING_DIMENSIONS,
    MODEL_NAME,
    SHOW_VECTOR_INDEX,
    VECTOR_INDEX,
    vector_index_problems,
)

SELECT_PENDING = """
MATCH (t:Trecho)
WHERE $force OR t.embedding IS NULL OR t.embedding_model IS NULL OR t.embedding_model <> $model
RETURN t.trecho_id AS trecho_id, t.texto AS texto
ORDER BY trecho_id
"""

WRITE_EMBEDDINGS = """
UNWIND $rows AS row
MATCH (t:Trecho {trecho_id: row.trecho_id})
SET t.embedding = row.embedding, t.embedding_model = $model
RETURN count(t) AS atualizados
"""

VERIFY = """
MATCH (t:Trecho)
RETURN count(t) AS total,
       count(t.embedding) AS com_embedding,
       min(size(t.embedding)) AS dimensao_min,
       max(size(t.embedding)) AS dimensao_max,
       collect(DISTINCT t.embedding_model) AS modelos
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
        records = session.run(SELECT_PENDING, force=args.force, model=MODEL_NAME).data()

    if args.limit:
        records = records[: args.limit]
    pending = [r for r in records if (r["texto"] or "").strip()]
    skipped = len(records) - len(pending)
    print(f"Trechos pendentes: {len(records)} (sem texto, ignorados: {skipped})")
    if args.dry_run or not pending:
        if args.dry_run:
            print("Dry-run: nenhuma escrita no Neo4j.")
        return 0

    from app.services.embeddings import SentenceEncoder, truncation_summary

    encoder = SentenceEncoder()
    print(f"Modelo carregado: {MODEL_NAME} (máx. {encoder.max_seq_length} tokens por texto)")
    if encoder.max_seq_length:
        report = truncation_summary(encoder.count_tokens([r["texto"] for r in pending]), encoder.max_seq_length)
        print(
            f"Truncamento: {report['acima_do_limite']}/{report['total']} trechos acima de {report['limite']} "
            f"tokens (mín. {report['minimo']}, mediana {report['mediana']:g}, máx. {report['maximo']}); "
            f"nesses, o embedding representa só os primeiros {report['limite']} tokens."
        )
    total = 0
    with driver.session(database=database) as session:
        for start in range(0, len(pending), args.batch_size):
            batch = pending[start:start + args.batch_size]
            vectors = encoder.encode([r["texto"] for r in batch], batch_size=args.batch_size)
            rows: List[Dict[str, Any]] = [
                {"trecho_id": r["trecho_id"], "embedding": v} for r, v in zip(batch, vectors)
            ]
            updated = session.execute_write(
                lambda tx: tx.run(WRITE_EMBEDDINGS, rows=rows, model=MODEL_NAME).single()["atualizados"]
            )
            total += updated
            print(f"Embeddings gravados: {total}/{len(pending)}")

        session.run("CALL db.awaitIndex($name, 300)", name=VECTOR_INDEX).consume()
        check = session.run(VERIFY).single().data()

    print(
        f"Concluído. Modelo={MODEL_NAME}; trechos atualizados={total}; "
        f"Trecho com embedding={check['com_embedding']}/{check['total']}; "
        f"dimensão min/max={check['dimensao_min']}/{check['dimensao_max']}; modelos={check['modelos']}"
    )
    if check["dimensao_min"] != EMBEDDING_DIMENSIONS or check["dimensao_max"] != EMBEDDING_DIMENSIONS:
        print(f"Erro: há embeddings fora de {EMBEDDING_DIMENSIONS} dimensões.", file=sys.stderr)
        return 1
    return 0


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
