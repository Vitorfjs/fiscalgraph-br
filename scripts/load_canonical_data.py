#!/usr/bin/env python3
"""Carrega os sete CSVs canônicos do FiscalGraph BR no Neo4j.

Características:
- valida cabeçalhos, chaves e referências antes de conectar ao banco;
- preserva CNPJ/códigos como strings, inclusive zeros à esquerda;
- usa MERGE para permitir reexecução idempotente;
- nunca apaga o conteúdo do banco;
- oferece --dry-run para validar os arquivos sem escrever no Neo4j.

Execute na raiz do repositório:
    python scripts/load_canonical_data.py --dry-run
    python scripts/load_canonical_data.py
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "processed" / "canonical"
CNPJ14 = re.compile(r"^[A-Z0-9]{12}[0-9]{2}$")
BASICO8 = re.compile(r"^[A-Z0-9]{8}$")

SCHEMAS: dict[str, list[str]] = {
    "fontes.csv": ["fonte_id", "nome", "orgao_responsavel", "url", "data_coleta", "competencia", "arquivo_origem"],
    "empresas.csv": ["cnpj_basico", "razao_social", "natureza_juridica", "porte", "capital_social", "fonte_id", "registro_origem"],
    "estabelecimentos.csv": ["cnpj", "cnpj_basico", "nome_fantasia", "situacao_cadastral", "data_inicio_atividade", "uf", "municipio", "fonte_id", "registro_origem"],
    "cnaes.csv": ["codigo", "descricao", "fonte_id", "registro_origem"],
    "estabelecimento_cnaes.csv": ["cnpj", "codigo", "principal", "fonte_id", "registro_origem"],
    "socios.csv": ["socio_id", "cnpj_basico", "nome", "tipo_pessoa", "qualificacao", "data_entrada", "fonte_id", "registro_origem"],
    "compliance.csv": ["registro_id", "tipo_registro", "orgao_responsavel", "numero_processo", "data_inicio", "data_fim", "situacao", "descricao", "observacoes", "fundamentacao_legal", "cnpj_sancionado", "fonte_id", "url_fonte", "registro_origem"],
}

KEYS: dict[str, tuple[str, ...]] = {
    "fontes.csv": ("fonte_id",),
    "empresas.csv": ("cnpj_basico",),
    "estabelecimentos.csv": ("cnpj",),
    "cnaes.csv": ("codigo",),
    "estabelecimento_cnaes.csv": ("cnpj", "codigo"),
    "socios.csv": ("socio_id",),
    "compliance.csv": ("registro_id",),
}

QUERIES: dict[str, str] = {
    "fontes.csv": """
        UNWIND $rows AS row
        MERGE (f:Fonte {fonte_id: row.fonte_id})
        SET f.nome = row.nome,
            f.orgao_responsavel = row.orgao_responsavel,
            f.url = row.url,
            f.data_coleta = row.data_coleta,
            f.competencia = row.competencia,
            f.arquivo_origem = row.arquivo_origem
    """,
    "empresas.csv": """
        UNWIND $rows AS row
        MATCH (f:Fonte {fonte_id: row.fonte_id})
        MERGE (e:Empresa {cnpj_basico: row.cnpj_basico})
        SET e.razao_social = row.razao_social,
            e.natureza_juridica = row.natureza_juridica,
            e.porte = row.porte,
            e.capital_social = row.capital_social
        MERGE (e)-[:ORIGINADO_DE {registro_origem: row.registro_origem}]->(f)
    """,
    "estabelecimentos.csv": """
        UNWIND $rows AS row
        MATCH (emp:Empresa {cnpj_basico: row.cnpj_basico})
        MATCH (f:Fonte {fonte_id: row.fonte_id})
        MERGE (e:Estabelecimento {cnpj: row.cnpj})
        SET e.cnpj_basico = row.cnpj_basico,
            e.nome_fantasia = row.nome_fantasia,
            e.situacao_cadastral = row.situacao_cadastral,
            e.data_inicio_atividade = row.data_inicio_atividade,
            e.uf = row.uf,
            e.municipio = row.municipio
        MERGE (emp)-[:POSSUI_ESTABELECIMENTO {registro_origem: row.registro_origem}]->(e)
        MERGE (e)-[:ORIGINADO_DE {registro_origem: row.registro_origem}]->(f)
    """,
    "cnaes.csv": """
        UNWIND $rows AS row
        MATCH (f:Fonte {fonte_id: row.fonte_id})
        MERGE (c:CNAE {codigo: row.codigo})
        SET c.descricao = row.descricao
        MERGE (c)-[:ORIGINADO_DE {registro_origem: row.registro_origem}]->(f)
    """,
    "socios.csv": """
        UNWIND $rows AS row
        MATCH (emp:Empresa {cnpj_basico: row.cnpj_basico})
        MATCH (f:Fonte {fonte_id: row.fonte_id})
        MERGE (s:Socio {socio_id: row.socio_id})
        SET s.nome = row.nome,
            s.tipo_pessoa = row.tipo_pessoa,
            s.qualificacao = row.qualificacao,
            s.data_entrada = row.data_entrada
        MERGE (s)-[r:PARTICIPA_DE {registro_origem: row.registro_origem}]->(emp)
        SET r.qualificacao = row.qualificacao,
            r.data_entrada = row.data_entrada
        MERGE (s)-[:ORIGINADO_DE {registro_origem: row.registro_origem}]->(f)
    """,
    "estabelecimento_cnaes.csv": """
        UNWIND $rows AS row
        MATCH (e:Estabelecimento {cnpj: row.cnpj})
        MATCH (c:CNAE {codigo: row.codigo})
        MERGE (e)-[r:EXERCE_CNAE {registro_origem: row.registro_origem}]->(c)
        SET r.principal = row.principal,
            r.fonte_id = row.fonte_id
    """,
    "compliance.csv": """
        UNWIND $rows AS row
        MATCH (e:Estabelecimento {cnpj: row.cnpj_sancionado})
        MATCH (f:Fonte {fonte_id: row.fonte_id})
        MERGE (s:Sancao {registro_id: row.registro_id})
        SET s.tipo_registro = row.tipo_registro,
            s.orgao_responsavel = row.orgao_responsavel,
            s.numero_processo = row.numero_processo,
            s.data_inicio = row.data_inicio,
            s.data_fim = row.data_fim,
            s.situacao = row.situacao,
            s.descricao = row.descricao,
            s.observacoes = row.observacoes,
            s.fundamentacao_legal = row.fundamentacao_legal,
            s.cnpj_sancionado = row.cnpj_sancionado,
            s.url_fonte = row.url_fonte
        MERGE (s)-[:APLICADA_A {cnpj_correspondencia: row.cnpj_sancionado, registro_origem: row.registro_origem}]->(e)
        MERGE (s)-[:ORIGINADO_DE {registro_origem: row.registro_origem}]->(f)
    """,
}


def read_table(directory: Path, filename: str) -> list[dict[str, str]]:
    path = directory / filename
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo canônico ausente: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = SCHEMAS[filename]
        if reader.fieldnames != expected:
            raise ValueError(
                f"Cabeçalho incompatível em {filename}.\n"
                f"Esperado: {expected}\nRecebido: {reader.fieldnames}"
            )
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def parse_boolean(value: str, field: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "sim"}:
        return True
    if normalized in {"false", "0", "não", "nao"}:
        return False
    raise ValueError(f"Valor booleano inválido em {field}: {value!r}")


def validate_tables(tables: dict[str, list[dict[str, str]]]) -> None:
    errors: list[str] = []

    # Verificação de chaves vazias e duplicadas.
    for filename, fields in KEYS.items():
        seen: set[tuple[str, ...]] = set()
        for line_number, row in enumerate(tables[filename], start=2):
            key = tuple((row.get(field) or "").strip() for field in fields)
            if any(not part for part in key):
                errors.append(f"{filename}:{line_number}: chave vazia em {fields}.")
            elif key in seen:
                errors.append(f"{filename}:{line_number}: chave duplicada em {fields}.")
            seen.add(key)

    fontes = {r["fonte_id"] for r in tables["fontes.csv"]}
    empresas = {r["cnpj_basico"] for r in tables["empresas.csv"]}
    estabelecimentos = {r["cnpj"] for r in tables["estabelecimentos.csv"]}
    cnaes = {r["codigo"] for r in tables["cnaes.csv"]}

    def check_source(filename: str) -> None:
        for line_number, row in enumerate(tables[filename], start=2):
            if row.get("fonte_id") not in fontes:
                errors.append(f"{filename}:{line_number}: fonte_id sem registro em fontes.csv.")

    for filename in ("empresas.csv", "estabelecimentos.csv", "cnaes.csv", "socios.csv", "estabelecimento_cnaes.csv", "compliance.csv"):
        check_source(filename)

    for line_number, row in enumerate(tables["empresas.csv"], start=2):
        if not BASICO8.fullmatch(row["cnpj_basico"]):
            errors.append(f"empresas.csv:{line_number}: cnpj_basico fora do formato estrutural de 8 caracteres.")

    for line_number, row in enumerate(tables["estabelecimentos.csv"], start=2):
        cnpj = row["cnpj"]
        if not CNPJ14.fullmatch(cnpj):
            errors.append(f"estabelecimentos.csv:{line_number}: CNPJ fora do formato estrutural de 14 caracteres.")
        if cnpj[:8] != row["cnpj_basico"]:
            errors.append(f"estabelecimentos.csv:{line_number}: cnpj_basico não corresponde ao CNPJ.")
        if row["cnpj_basico"] not in empresas:
            errors.append(f"estabelecimentos.csv:{line_number}: empresa não encontrada.")

    for line_number, row in enumerate(tables["socios.csv"], start=2):
        if row["cnpj_basico"] not in empresas:
            errors.append(f"socios.csv:{line_number}: empresa não encontrada.")

    pairs: set[tuple[str, str]] = set()
    for line_number, row in enumerate(tables["estabelecimento_cnaes.csv"], start=2):
        pair = (row["cnpj"], row["codigo"])
        if pair in pairs:
            errors.append(f"estabelecimento_cnaes.csv:{line_number}: par CNPJ/CNAE duplicado.")
        pairs.add(pair)
        if row["cnpj"] not in estabelecimentos:
            errors.append(f"estabelecimento_cnaes.csv:{line_number}: estabelecimento não encontrado.")
        if row["codigo"] not in cnaes:
            errors.append(f"estabelecimento_cnaes.csv:{line_number}: CNAE não encontrado.")
        try:
            row["principal"] = parse_boolean(row["principal"], "principal")
        except ValueError as exc:
            errors.append(f"estabelecimento_cnaes.csv:{line_number}: {exc}")

    for line_number, row in enumerate(tables["compliance.csv"], start=2):
        cnpj = row["cnpj_sancionado"]
        if not CNPJ14.fullmatch(cnpj):
            errors.append(f"compliance.csv:{line_number}: cnpj_sancionado fora do formato estrutural.")
        if cnpj not in estabelecimentos:
            errors.append(f"compliance.csv:{line_number}: CNPJ sancionado sem estabelecimento exato.")

    if errors:
        raise ValueError("Validação anterior à carga encontrou problemas:\n- " + "\n- ".join(errors))


def batched(items: list[dict[str, Any]], size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def write_table(session: Any, filename: str, rows: list[dict[str, Any]], batch_size: int) -> None:
    query = QUERIES[filename]
    for batch in batched(rows, batch_size):
        session.run(query, rows=batch).consume()


def load_all(tables: dict[str, list[dict[str, Any]]], driver: Any, batch_size: int, database: str) -> None:
    order = (
        "fontes.csv",
        "empresas.csv",
        "estabelecimentos.csv",
        "cnaes.csv",
        "socios.csv",
        "estabelecimento_cnaes.csv",
        "compliance.csv",
    )
    with driver.session(database=database) as session:
        for filename in order:
            rows = tables[filename]
            write_table(session, filename, rows, batch_size)
            print(f"Carregado: {filename} ({len(rows)} registros)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega o contrato canônico no Neo4j.")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true", help="Valida os CSVs sem conectar ao Neo4j.")
    args = parser.parse_args()

    if args.batch_size < 1:
        print("ERRO: --batch-size deve ser maior que zero.", file=sys.stderr)
        return 2

    try:
        tables = {filename: read_table(args.directory, filename) for filename in SCHEMAS}
        validate_tables(tables)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    print("Validação dos sete CSVs concluída.")
    for filename, rows in tables.items():
        print(f"  {filename}: {len(rows)} registros")

    if args.dry_run:
        print("DRY-RUN: nenhuma conexão ou escrita foi realizada no Neo4j.")
        return 0

    # Importa cliente e dotenv somente quando a execução realmente irá conectar ao banco.
    from dotenv import load_dotenv
    from neo4j import GraphDatabase
    from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable

    load_dotenv(ROOT / ".env")
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    if not password or password == "change_this_password_before_starting":
        print("ERRO: configure NEO4J_PASSWORD no .env local.", file=sys.stderr)
        return 2

    try:
        with GraphDatabase.driver(uri, auth=(user, password)) as driver:
            driver.verify_connectivity()
            load_all(tables, driver, args.batch_size, database)
        print("Carga concluída. O processo usa MERGE e não apaga dados existentes.")
        return 0
    except AuthError:
        print("ERRO: autenticação recusada. Confira NEO4J_USER/NEO4J_PASSWORD.", file=sys.stderr)
        return 1
    except ServiceUnavailable:
        print("ERRO: Neo4j indisponível. Confira o container e a porta 7687.", file=sys.stderr)
        return 1
    except Neo4jError as exc:
        print(f"ERRO Neo4j: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERRO inesperado: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
