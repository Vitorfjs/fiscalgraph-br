#!/usr/bin/env python3
"""Aplica o schema declarativo do FiscalGraph BR de forma idempotente no Neo4j."""
from __future__ import annotations
import argparse, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_CONSTRAINTS = {
    "empresa_cnpj_basico_unique", "estabelecimento_cnpj_unique",
    "socio_socio_id_unique", "cnae_codigo_unique", "sancao_registro_id_unique",
    "fonte_fonte_id_unique", "trecho_trecho_id_unique",
}
EXPECTED_INDEXES = {
    "estabelecimento_situacao_cadastral_idx", "estabelecimento_localizacao_idx",
    "empresa_porte_idx", "sancao_tipo_registro_idx", "sancao_numero_processo_idx",
    "fiscalgraph_text_fulltext",
}

def split_cypher_statements(source: str) -> list[str]:
    lines = [line for line in source.splitlines() if not line.lstrip().startswith("//")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]

def apply_schema(driver, database: str, schema_path: Path) -> None:
    statements = split_cypher_statements(schema_path.read_text(encoding="utf-8"))
    if not statements:
        raise ValueError(f"Nenhum comando Cypher encontrado em {schema_path}.")
    with driver.session(database=database) as session:
        for statement in statements:
            session.run(statement).consume()
        session.run("CALL db.awaitIndexes(300)").consume()
        constraints = session.run(
            "SHOW CONSTRAINTS YIELD name RETURN collect(name) AS names"
        ).single()["names"]
        missing = EXPECTED_CONSTRAINTS - set(constraints or [])
        if missing:
            raise RuntimeError("Constraints ausentes: " + ", ".join(sorted(missing)))
        indexes = session.run(
            "SHOW INDEXES YIELD name, state WHERE name IN $names RETURN name, state",
            names=sorted(EXPECTED_INDEXES),
        ).data()
        states = {row["name"]: row["state"] for row in indexes}
        missing = EXPECTED_INDEXES - set(states)
        offline = {name for name, state in states.items() if state != "ONLINE"}
        if missing or offline:
            details = []
            if missing:
                details.append("ausentes: " + ", ".join(sorted(missing)))
            if offline:
                details.append("não ONLINE: " + ", ".join(
                    f"{name} ({states[name]})" for name in sorted(offline)
                ))
            raise RuntimeError("Índices não validados: " + "; ".join(details))
    print(f"Schema aplicado e validado: {len(statements)} comandos.")
    print(f"Constraints verificadas: {len(EXPECTED_CONSTRAINTS)}.")
    print(f"Índices de busca verificados ONLINE: {len(EXPECTED_INDEXES)}.")

def main() -> int:
    parser = argparse.ArgumentParser(description="Aplica e valida o schema LPG do FiscalGraph BR.")
    parser.add_argument("--schema", type=Path, default=ROOT / "cypher" / "01_schema_fiscalgraph.cypher")
    parser.add_argument("--database", default=None)
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv
        from neo4j import GraphDatabase
        from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable
    except ImportError:
        print("Dependências ausentes. Instale requirements.txt.", file=sys.stderr)
        return 2
    load_dotenv(ROOT / ".env")
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    database = args.database or os.getenv("NEO4J_DATABASE", "neo4j")
    if not password or password == "change_this_password_before_starting":
        print("Configure NEO4J_PASSWORD no .env ou no ambiente.", file=sys.stderr)
        return 2
    if not args.schema.is_file():
        print(f"Arquivo de schema não encontrado: {args.schema}", file=sys.stderr)
        return 2
    try:
        with GraphDatabase.driver(uri, auth=(user, password)) as driver:
            driver.verify_connectivity()
            apply_schema(driver, database, args.schema)
    except AuthError:
        print("Falha de autenticação. Confira NEO4J_USER e NEO4J_PASSWORD.", file=sys.stderr)
        return 1
    except ServiceUnavailable:
        print("Neo4j indisponível. Confira NEO4J_URI e a porta 7687.", file=sys.stderr)
        return 1
    except (Neo4jError, OSError, RuntimeError, ValueError) as exc:
        print(f"Falha ao aplicar/validar schema: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
