#!/usr/bin/env python3
"""Carrega nós Trecho e relações MENCIONA candidatas no Neo4j.

Requer o schema de dev3 integrado (constraint de unicidade em ``Trecho.trecho_id``)
e um arquivo ``.env`` local com NEO4J_URI, NEO4J_USER e NEO4J_PASSWORD.

Relações criadas:
- (Trecho)-[:EXTRATO_DE]->(registro de compliance)  quando o registro existir no grafo;
- (Trecho)-[:ORIGINADO_DE]->(Fonte)                  quando a fonte existir no grafo;
- (Trecho)-[:MENCIONA {metodo, status:'CANDIDATA', inicio, fim}]->(Estabelecimento)
  somente por igualdade EXATA entre o CNPJ mencionado e ``Estabelecimento.cnpj``.

O registro de compliance é procurado pelos rótulos ``Sancao`` (modelagem dev3) ou
``RegistroCompliance`` (contrato do coordenador), sempre por ``registro_id``.
Menções de organização (NER) nunca geram relação: ficam apenas no JSONL e no
atributo ``mencoes_json`` do Trecho. Nenhum vínculo é criado por semelhança de nome.

Uso:
    python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parents[2]

from pipeline.text_to_graph.extractor import normalize_organization_name

UPSERT_CHUNKS = """
UNWIND $rows AS row
MERGE (t:Trecho {trecho_id: row.trecho_id})
SET t.texto = row.texto,
    t.registro_id = row.registro_id,
    t.fonte_id = row.fonte_id,
    t.url_fonte = row.url_fonte,
    t.registro_origem = row.registro_origem,
    t.metodo_extracao = row.metodo_extracao,
    t.mencoes_json = row.mencoes_json
WITH t, row
OPTIONAL MATCH (r) WHERE (r:Sancao OR r:RegistroCompliance) AND r.registro_id = row.registro_id
WITH t, row, head(collect(r)) AS r
FOREACH (_ IN CASE WHEN r IS NULL THEN [] ELSE [1] END | MERGE (t)-[:EXTRATO_DE]->(r))
WITH t, row, r
OPTIONAL MATCH (f:Fonte {fonte_id: row.fonte_id})
WITH t, r, head(collect(f)) AS f
FOREACH (_ IN CASE WHEN f IS NULL THEN [] ELSE [1] END | MERGE (t)-[:ORIGINADO_DE]->(f))
RETURN t.trecho_id AS trecho_id, r IS NOT NULL AS registro_encontrado, f IS NOT NULL AS fonte_encontrada
"""

LINK_MENTIONS = """
UNWIND $rows AS row
MATCH (t:Trecho {trecho_id: row.trecho_id})
OPTIONAL MATCH (e:Estabelecimento {cnpj: row.cnpj})
FOREACH (_ IN CASE WHEN e IS NULL THEN [] ELSE [1] END |
    MERGE (t)-[m:MENCIONA {inicio: row.inicio, fim: row.fim}]->(e)
    SET m.metodo = row.metodo, m.status = 'CANDIDATA')
RETURN row.cnpj AS cnpj, e IS NOT NULL AS linked
"""

LINK_ORGANIZATION_MENTIONS = """
UNWIND $rows AS row
MATCH (t:Trecho {trecho_id: row.trecho_id})
MATCH (e:Empresa {cnpj_basico: row.cnpj_basico})
MERGE (t)-[m:MENCAO_NOME {inicio: row.inicio, fim: row.fim}]->(e)
SET m.metodo = row.metodo,
    m.status = 'CANDIDATA',
    m.valor_normalizado = row.valor_normalizado
RETURN row.cnpj_basico AS cnpj_basico
"""

CHUNK_FIELDS = ("trecho_id", "texto", "url_fonte", "registro_origem", "metodo_extracao", "registro_id", "fonte_id")


def positive_int(value: str) -> int:
    """Valida se o valor informado para lote é um inteiro positivo maior ou igual a 1."""
    try:
        val = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' não é um número inteiro válido.")
    if val < 1:
        raise argparse.ArgumentTypeError(f"batch-size deve ser maior ou igual a 1 (recebido: {value}).")
    return val


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Lê o JSONL, ignorando linhas vazias e apontando a linha em caso de JSON inválido."""
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido em {path}:{number}: {exc}") from exc


def batched(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def chunk_row(item: dict[str, Any]) -> dict[str, Any]:
    """Converte um trecho do JSONL em parâmetros da query (Neo4j não armazena mapas aninhados)."""
    row = {key: item.get(key) or "" for key in CHUNK_FIELDS}
    row["mencoes_json"] = json.dumps(item.get("mencoes", []), ensure_ascii=False)
    return row


def mention_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Somente menções de CNPJ podem virar MENCIONA (correspondência exata)."""
    rows = []
    for mention in item.get("mencoes", []):
        if mention.get("tipo") != "CNPJ" or not mention.get("valor"):
            continue
        rows.append({
            "trecho_id": item["trecho_id"],
            "cnpj": mention["valor"],
            "metodo": mention.get("metodo", "desconhecido"),
            "inicio": mention.get("inicio"),
            "fim": mention.get("fim"),
        })
    return rows


def build_organization_index(companies_csv: Path) -> dict[str, str | None]:
    """Indexa nomes legais normalizados; colisões entre CNPJs viram ambiguidades (None)."""
    index: dict[str, str | None] = {}
    with companies_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"cnpj_basico", "razao_social"}.issubset(set(reader.fieldnames or [])):
            raise ValueError("CSV de empresas precisa conter cnpj_basico e razao_social.")
        for row in reader:
            normalized = normalize_organization_name(row.get("razao_social") or "")
            cnpj_basico = (row.get("cnpj_basico") or "").strip()
            if not normalized or not cnpj_basico:
                continue
            previous = index.get(normalized)
            if normalized in index and previous != cnpj_basico:
                index[normalized] = None
            else:
                index[normalized] = cnpj_basico
    return index


def organization_rows(
    item: dict[str, Any], organization_index: dict[str, str | None]
) -> list[dict[str, Any]]:
    """Resolve apenas nome normalizado idêntico e não ambíguo; nunca usa fuzzy matching."""
    rows: list[dict[str, Any]] = []
    for mention in item.get("mencoes", []):
        if mention.get("tipo") != "ORGANIZACAO":
            continue
        normalized = mention.get("valor_normalizado") or normalize_organization_name(
            str(mention.get("valor") or "")
        )
        cnpj_basico = organization_index.get(normalized)
        if not cnpj_basico:
            continue
        rows.append({
            "trecho_id": item["trecho_id"],
            "cnpj_basico": cnpj_basico,
            "valor_normalizado": normalized,
            "inicio": mention.get("inicio"),
            "fim": mention.get("fim"),
            "metodo": mention.get("metodo", "spacy_ner_pt_core_news_sm"),
        })
    return rows


def summarize(items: list[dict[str, Any]]) -> dict[str, int]:
    """Contagens que não dependem do banco (úteis para --dry-run)."""
    cnpj = sum(1 for i in items for m in i.get("mencoes", []) if m.get("tipo") == "CNPJ")
    org = sum(1 for i in items for m in i.get("mencoes", []) if m.get("tipo") == "ORGANIZACAO")
    return {"trechos": len(items), "mencoes_cnpj": cnpj, "mencoes_org": org}


def load(
    items: list[dict[str, Any]],
    driver: Any,
    batch_size: int = 200,
    database: str | None = None,
    organization_index: dict[str, str | None] | None = None,
) -> dict[str, int]:
    stats = {
        "trechos_carregados": 0,
        "registros_nao_encontrados": 0,
        "fontes_nao_encontradas": 0,
        "mencoes_cnpj_ligadas": 0,
        "mencoes_cnpj_nao_resolvidas": 0,
        "mencoes_org_candidatas_ligadas": 0,
        "mencoes_org_sem_correspondencia_unica": 0,
        "mencoes_org_nao_ligadas": 0,
    }
    organization_index = organization_index or {}
    with driver.session(database=database) as session:
        for batch in batched(items, batch_size):
            records = session.run(UPSERT_CHUNKS, rows=[chunk_row(i) for i in batch]).data()
            stats["trechos_carregados"] += len(records)
            stats["registros_nao_encontrados"] += sum(1 for r in records if not r["registro_encontrado"])
            stats["fontes_nao_encontradas"] += sum(1 for r in records if not r["fonte_encontrada"])

            rows = [row for item in batch for row in mention_rows(item)]
            if rows:
                linked = session.run(LINK_MENTIONS, rows=rows).data()
                stats["mencoes_cnpj_ligadas"] += sum(1 for r in linked if r["linked"])
                stats["mencoes_cnpj_nao_resolvidas"] += sum(1 for r in linked if not r["linked"])
            all_org_mentions = [
                (item, mention)
                for item in batch for mention in item.get("mencoes", [])
                if mention.get("tipo") == "ORGANIZACAO"
            ]
            org_rows = [
                row for item in batch for row in organization_rows(item, organization_index)
            ]
            if org_rows:
                org_linked = session.run(LINK_ORGANIZATION_MENTIONS, rows=org_rows).data()
                stats["mencoes_org_candidatas_ligadas"] += len(org_linked)
            stats["mencoes_org_sem_correspondencia_unica"] += len(all_org_mentions) - len(org_rows)
            stats["mencoes_org_nao_ligadas"] += len(all_org_mentions) - len(org_rows)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carrega trechos.jsonl no Neo4j")
    parser.add_argument("--input", type=Path, required=True, help="Arquivo trechos.jsonl gerado pelo extractor")
    parser.add_argument(
        "--companies-csv",
        type=Path,
        default=ROOT / "data" / "processed" / "canonical" / "empresas.csv",
        help="CSV canônico para resolução nominal exata e unívoca",
    )
    parser.add_argument("--batch-size", type=positive_int, default=200, help="Tamanho do lote (deve ser >= 1)")
    parser.add_argument("--database", type=str, default=None, help="Nome do banco de dados Neo4j (opcional)")
    parser.add_argument("--dry-run", action="store_true", help="Apenas lê e resume o JSONL, sem conectar ao banco")
    args = parser.parse_args(argv)

    try:
        items = list(read_jsonl(args.input))
    except (OSError, ValueError) as exc:
        print(f"Erro ao ler {args.input}: {exc}", file=sys.stderr)
        return 1

    summary = summarize(items)
    try:
        organization_index = build_organization_index(args.companies_csv)
    except (OSError, ValueError) as exc:
        print(f"Erro ao carregar índice nominal {args.companies_csv}: {exc}", file=sys.stderr)
        return 1
    resolved_org = sum(
        len(organization_rows(item, organization_index)) for item in items
    )
    print(f"JSONL: {summary['trechos']} trechos, {summary['mencoes_cnpj']} menções CNPJ, "
          f"{summary['mencoes_org']} menções ORGANIZACAO")
    print(f"Menções ORGANIZACAO com nome normalizado único no catálogo: {resolved_org}")
    if args.dry_run:
        print("Dry-run: nenhuma escrita no Neo4j.")
        return 0

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
            stats = load(
                items, driver, args.batch_size, database=database,
                organization_index=organization_index,
            )
    except AuthError:
        print("Falha de autenticação. Confira NEO4J_USER e NEO4J_PASSWORD no .env.", file=sys.stderr)
        return 1
    except ServiceUnavailable:
        print("Neo4j não está acessível. Inicie o Docker Compose e confira a porta 7687.", file=sys.stderr)
        return 1
    except Neo4jError as exc:
        print(f"Erro retornado pelo Neo4j: {exc}", file=sys.stderr)
        return 1

    print(f"Trechos carregados: {stats['trechos_carregados']}")
    print(f"Registros de compliance não encontrados no grafo: {stats['registros_nao_encontrados']}")
    print(f"Fontes não encontradas no grafo: {stats['fontes_nao_encontradas']}")
    print(f"Menções CNPJ ligadas como CANDIDATA: {stats['mencoes_cnpj_ligadas']}")
    print(f"Menções CNPJ não resolvidas (sem Estabelecimento exato): {stats['mencoes_cnpj_nao_resolvidas']}")
    print(f"Menções ORGANIZACAO ligadas por nome normalizado exato e único: {stats['mencoes_org_candidatas_ligadas']}")
    print(f"Menções ORGANIZACAO sem correspondência nominal única: {stats['mencoes_org_sem_correspondencia_unica']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())