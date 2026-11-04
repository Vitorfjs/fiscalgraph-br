"""Verifica a conectividade com a instância local Neo4j."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable, AuthError

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD")


def main() -> int:
    if not PASSWORD or PASSWORD == "change_this_password_before_starting":
        print("Configure NEO4J_PASSWORD no arquivo .env antes de executar.")
        return 2

    try:
        with GraphDatabase.driver(URI, auth=(USER, PASSWORD)) as driver:
            driver.verify_connectivity()
            with driver.session() as session:
                record = session.run("RETURN 1 AS ok, datetime() AS checked_at").single()
                if not record or record["ok"] != 1:
                    print("A conexão foi aberta, mas a consulta de verificação falhou.")
                    return 1
                print(f"Neo4j conectado em {URI}. Verificação: {record['checked_at']}.")
                print("Ambiente pronto para receber o schema LPG.")
                return 0
    except AuthError:
        print("Falha de autenticação. Confira NEO4J_USER e NEO4J_PASSWORD no .env.")
        return 1
    except ServiceUnavailable:
        print("Neo4j não está acessível. Inicie o Docker Compose e confira a porta 7687.")
        return 1
    except Neo4jError as exc:
        print(f"Erro retornado pelo Neo4j: {exc}")
        return 1
    except Exception as exc:  # falha inesperada, mantendo mensagem útil
        print(f"Falha inesperada ao verificar Neo4j: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
