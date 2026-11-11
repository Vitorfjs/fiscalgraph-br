"""Aplicação Streamlit do FiscalGraph BR: consulta real e modo de demonstração."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable
from streamlit_agraph import agraph, Config, Edge, Node

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.services.mock_service import get_mock_response
from app.services.orchestrator import answer_question
from app.services.retrieval import GraphHybridRetriever
from app.services.source_adapter import normalize_source


@st.cache_resource(show_spinner="Conectando ao Neo4j e carregando o modelo de embeddings...")
def get_retriever() -> GraphHybridRetriever:
    """Mantém driver e SentenceEncoder vivos entre as interações do Streamlit."""
    return GraphHybridRetriever.from_env()


def render_payload(payload: dict) -> None:
    for warning in payload.get("warnings", []):
        st.warning(warning)

    if payload.get("abstained"):
        st.error(payload.get("answer", "O sistema se absteve de responder."))
    else:
        st.success(payload.get("answer", "Busca concluída."))

    sources = payload.get("sources", [])
    if sources:
        with st.expander("Fontes e evidências utilizadas", expanded=True):
            for raw_source in sources:
                source = normalize_source(raw_source)
                st.markdown(f"**{source['label']} — ID:** `{source['id'] or 'N/A'}`")
                if source["excerpt"]:
                    st.markdown(f"> {source['excerpt']}")
                if source["url"]:
                    st.markdown(f"[Acessar documento original]({source['url']})")
                st.divider()

    if payload.get("cypher"):
        with st.expander("Consulta Cypher"):
            st.code(payload["cypher"], language="cypher")

    relevance = payload.get("retrieval_relevance")
    if relevance is not None:
        st.caption(
            f"Relevância normalizada da recuperação: {relevance:.3f}. "
            "Esse valor não representa probabilidade de fraude ou irregularidade."
        )

    nodes_data = payload.get("nodes", [])
    relationships_data = payload.get("relationships", [])
    if not nodes_data:
        st.info("Nenhum subgrafo foi retornado para esta consulta.")
        return

    graph_nodes = []
    graph_edges = []
    node_ids = {node_data.get("id") for node_data in nodes_data}
    for node_data in nodes_data:
        properties = node_data.get("properties") or {}
        tooltip = "\n".join(f"{key}: {value}" for key, value in properties.items())
        graph_nodes.append(
            Node(id=node_data["id"], label=node_data["label"], title=tooltip, size=25)
        )

    for relationship in relationships_data:
        source = relationship.get("source")
        target = relationship.get("target")
        if source not in node_ids or target not in node_ids:
            continue
        properties = relationship.get("properties") or {}
        relation_type = relationship.get("type", "UNKNOWN")
        is_candidate = (
            relation_type == "MENCIONA"
            and properties.get("status") == "CANDIDATA"
        )
        edge_label = f"{relation_type} (CANDIDATA)" if is_candidate else relation_type
        graph_edges.append(
            Edge(
                source=source,
                target=target,
                label=edge_label,
                color="#FF4B4B" if is_candidate else "#4A90E2",
            )
        )

    st.subheader("Subgrafo retornado pela recuperação")
    agraph(
        nodes=graph_nodes,
        edges=graph_edges,
        config=Config(width="100%", height=500, directed=True, physics=True, hierarchical=False),
    )
    st.caption(
        "Vermelho: menção candidata que exige validação. "
        "As arestas exibidas são somente as retornadas pelo Neo4j."
    )


st.set_page_config(page_title="FiscalGraph BR", page_icon="🔎", layout="wide")
st.title("FiscalGraph BR")
st.caption("Consulta explicável de informações públicas de compliance empresarial.")

st.info(
    "Protótipo acadêmico. Registros públicos, coincidências cadastrais e menções textuais "
    "não comprovam fraude, irregularidade atual ou responsabilidade de terceiros."
)

with st.expander("Status da conexão Neo4j"):
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")
    if not password or password == "change_this_password_before_starting":
        st.warning("Configure NEO4J_PASSWORD no arquivo .env para habilitar a consulta real.")
    else:
        try:
            with GraphDatabase.driver(uri, auth=(user, password)) as driver:
                driver.verify_connectivity()
                with driver.session(database=os.getenv("NEO4J_DATABASE") or None) as session:
                    record = session.run(
                        "CALL { MATCH (n) RETURN count(n) AS nodes } "
                        "CALL { MATCH ()-[r]->() RETURN count(r) AS relationships } "
                        "RETURN nodes, relationships"
                    ).single()
            col1, col2 = st.columns(2)
            col1.metric("Nós", record["nodes"] if record else 0)
            col2.metric("Relacionamentos", record["relationships"] if record else 0)
        except AuthError:
            st.error("Falha de autenticação no Neo4j. Confira NEO4J_USER e NEO4J_PASSWORD.")
        except ServiceUnavailable:
            st.error("Neo4j indisponível. Inicie o serviço e confira NEO4J_URI.")

st.sidebar.header("Modo de execução")
mode = st.sidebar.radio(
    "Selecione o modo",
    ["Consulta real (Neo4j)", "Demonstração (Mock)"],
    help="A demonstração usa fixtures sintéticas e não executa recuperação.",
)
top_k = st.sidebar.slider("Quantidade de evidências (top_k)", min_value=1, max_value=10, value=5)
mock_scenario = st.sidebar.radio(
    "Cenário de demonstração",
    ["Sucesso (grafo e fontes)", "Abstenção (sem conclusão)"],
    disabled=(mode != "Demonstração (Mock)"),
)

with st.form("query_form"):
    question = st.text_input(
        "Pergunta para o grafo",
        placeholder="Ex.: Quais registros públicos aparecem relacionados a este CNPJ?",
    )
    submitted = st.form_submit_button("Pesquisar")

if submitted:
    if not question.strip():
        st.warning("Digite uma pergunta antes de pesquisar.")
    elif mode == "Demonstração (Mock)":
        st.caption("Modo demonstração: os dados exibidos são sintéticos e independem da pergunta digitada.")
        payload = get_mock_response("sucesso" if mock_scenario.startswith("Sucesso") else "abstencao")
        render_payload(payload)
    else:
        try:
            with st.spinner("Consultando os índices vetorial e full-text e expandindo o grafo..."):
                retriever = get_retriever()
                payload = answer_question(question, top_k=top_k, retriever=retriever)
            render_payload(payload)
        except (RuntimeError, ValueError, OSError) as exc:
            st.error("Não foi possível executar a consulta real.")
            with st.expander("Detalhes técnicos"):
                st.code(str(exc))
        except Exception as exc:
            st.error("Ocorreu um erro inesperado durante a consulta.")
            with st.expander("Detalhes técnicos"):
                st.code(f"{type(exc).__name__}: {exc}")
else:
    st.caption("Escolha o modo, informe uma pergunta e pressione Pesquisar.")
