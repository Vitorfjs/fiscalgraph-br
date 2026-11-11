"""Tela inicial do FiscalGraph BR integrando teste de DB e interface Mock (Dev6)."""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable
from streamlit_agraph import agraph, Node, Edge, Config

# Adaptador Mock
from services.mock_service import get_mock_response

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

st.set_page_config(page_title="FiscalGraph BR", page_icon="🔎", layout="wide")
st.title("FiscalGraph BR")
st.caption("Análise explicável de vínculos societários e registros públicos de compliance")

st.info(
    "Protótipo acadêmico. Vínculos societários ou registros públicos, isoladamente, "
    "não comprovam fraude, sonegação ou responsabilidade de terceiros."
)

# --- 1. VERIFICAÇÃO DO BANCO DE DADOS (Código original mantido) ---
uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD")

with st.expander("🔌 Status da Conexão Neo4j (Opcional para esta etapa)"):
    if not password:
        st.warning("Configure as variáveis do arquivo .env e inicie o Neo4j pelo Docker Compose.")
    else:
        try:
            with GraphDatabase.driver(uri, auth=(user, password)) as driver:
                driver.verify_connectivity()
                with driver.session() as session:
                    query_db = """
                    CALL { MATCH (n) RETURN count(n) AS nodes }
                    CALL { MATCH ()-[r]->() RETURN count(r) AS relationships }
                    RETURN nodes, relationships
                    """
                    record = session.run(query_db).single()
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

st.divider()

# --- 2. INTERFACE DE BUSCA (Dev6) ---
st.subheader("Consulta ao conhecimento (Modo Mock)")

# Menu lateral para controle dos mocks
st.sidebar.header("🛠️ Módulo Dev6 - Mock")
cenario = st.sidebar.radio(
    "Escolha a Fixture:",
    ["Sucesso (Grafo e Fontes)", "Abstenção (Sem conclusão)"]
)

query = st.text_input("Pergunta para o grafo", placeholder="Ex.: Quais empresas estão ligadas a uma empresa que possui registro de sanção?")

if st.button("Pesquisar") or query:
    tipo_cenario = "sucesso" if cenario == "Sucesso (Grafo e Fontes)" else "abstencao"
    payload = get_mock_response(tipo_cenario)

    # Avisos
    if payload.get("warnings"):
        for warning in payload["warnings"]:
            st.warning(f"⚠️ **Aviso:** {warning}")

    # Resposta / Abstenção
    if payload.get("abstained"):
        st.error(payload.get("answer", "O sistema se absteve de responder."))
    else:
        st.success(payload.get("answer", "Busca concluída com sucesso."))

    # Fontes e Evidências
    if payload.get("sources"):
        with st.expander("📚 Fontes e Evidências Utilizadas"):
            for source in payload["sources"]:
                st.markdown(f"**ID da Fonte:** `{source.get('fonte_id', 'N/A')}`")
                st.markdown(f"> {source.get('texto', 'Sem texto disponível.')}")
                if source.get("url_fonte"):
                    st.markdown(f"🔗 [Acessar documento original]({source['url_fonte']})")
                st.divider()

    # Cypher
    if payload.get("cypher"):
        with st.expander("💻 Consulta Cypher (Neo4j)"):
            st.code(payload["cypher"], language="cypher")

    # Relevância
    if payload.get("retrieval_relevance") is not None:
        st.info(f"Índice de Relevância de Recuperação (Não é probabilidade de fraude): {payload['retrieval_relevance']}")

    # Subgrafo
    nodes_data = payload.get("nodes", [])
    rels_data = payload.get("relationships", [])

    if nodes_data and rels_data:
        st.write("### 🕸️ Visualização do Subgrafo")
        
        nodes, edges = [], []

        for n in nodes_data:
            tooltip = "\n".join([f"{k}: {v}" for k, v in n.get("properties", {}).items()])
            nodes.append(Node(id=n["id"], label=n["label"], title=tooltip, size=25))

        for r in rels_data:
            props = r.get("properties", {})
            tipo = r.get("type", "UNKNOWN")
            
            is_candidata = tipo == "MENCIONA" and props.get("status") == "CANDIDATA"
            edge_color = "#FF4B4B" if is_candidata else "#4A90E2"
            edge_label = f"{tipo} (CANDIDATA)" if is_candidata else tipo
            
            edges.append(Edge(source=r["source"], target=r["target"], label=edge_label, color=edge_color))

        config = Config(width="100%", height=500, directed=True, physics=True, hierarchical=False)
        agraph(nodes=nodes, edges=edges, config=config)
        st.caption("🔴 Vermelho: Menção Candidata (Requer validação) | 🔵 Azul: Vínculo Extraído")
    else:
        st.info("Nenhum subgrafo retornado para visualização nesta consulta.")