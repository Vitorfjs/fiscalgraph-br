"""Tela inicial mínima do FiscalGraph BR; a busca GraphRAG será adicionada depois."""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

st.set_page_config(page_title="FiscalGraph BR", page_icon="🔎", layout="wide")
st.title("FiscalGraph BR")
st.caption("Análise explicável de vínculos societários e registros públicos de compliance")

st.info(
    "Protótipo acadêmico. Vínculos societários ou registros públicos, isoladamente, "
    "não comprovam fraude, sonegação ou responsabilidade de terceiros."
)

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD")

st.subheader("Estado da conexão com o banco")
if not password:
    st.warning("Configure as variáveis do arquivo .env e inicie o Neo4j pelo Docker Compose.")
else:
    try:
        with GraphDatabase.driver(uri, auth=(user, password)) as driver:
            driver.verify_connectivity()
            with driver.session() as session:
                query = """
                CALL {
                    MATCH (n) RETURN count(n) AS nodes
                }
                CALL {
                    MATCH ()-[r]->() RETURN count(r) AS relationships
                }
                RETURN nodes, relationships
                """
                record = session.run(query).single()
                nodes_count = record["nodes"] if record else 0
                rels_count = record["relationships"] if record else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Banco", "Conectado")
        c2.metric("Nós", nodes_count)
        c3.metric("Relacionamentos", rels_count)
    except AuthError:
        st.error("Falha de autenticação. Confira as credenciais no .env.")
    except ServiceUnavailable:
        st.error("Neo4j indisponível. Confira se o container está em execução.")

st.subheader("Consulta ao conhecimento")
st.text_area(
    "Pergunta para o grafo",
    placeholder="Ex.: Quais empresas estão ligadas a uma empresa que possui registro de sanção?",
    disabled=True,
    help="A busca será habilitada após a ingestão e a implementação do mecanismo GraphRAG.",
)
st.caption("Próximo marco: criar o schema, carregar a amostra de dados e validar as primeiras consultas Cypher.")
