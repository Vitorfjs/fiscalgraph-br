"""Aplicação Streamlit do FiscalGraph BR: consulta real e modo de demonstração."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from streamlit_agraph import Config, agraph

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.services import mock_service, orchestrator, retrieval, source_adapter, ui_helpers, llm_cypher

# Re-exportações explícitas para compatibilidade e organização de testes.
build_graph_elements = ui_helpers.build_graph_elements
check_neo4j_status = ui_helpers.check_neo4j_status
sanitize_error_message = ui_helpers.sanitize_error_message


@st.cache_resource(show_spinner="Conectando ao Neo4j e carregando o modelo de embeddings...")
def get_retriever() -> retrieval.GraphHybridRetriever:
    """Mantém driver e SentenceEncoder vivos entre as interações do Streamlit."""
    return retrieval.GraphHybridRetriever.from_env()


def _render_sources(sources: list) -> None:
    if not sources:
        return
    with st.expander(f"Fontes e evidências utilizadas ({len(sources)})", expanded=True):
        for raw_source in sources:
            source = source_adapter.normalize_source(raw_source)
            st.markdown(f"**{source['label']} — ID:** `{source['id'] or 'N/A'}`")
            if source["excerpt"]:
                st.markdown(f"> {source['excerpt']}")
            if source["url"]:
                st.markdown(f"[Acessar documento original]({source['url']})")
            else:
                st.caption("URL não informada na origem desta evidência.")
            st.divider()


def _render_graph_section(nodes_data: list, relationships_data: list) -> None:
    if not nodes_data:
        st.info("Nenhum subgrafo foi retornado para esta consulta.")
        return

    graph_nodes, graph_edges, candidate_count = ui_helpers.build_graph_elements(
        nodes_data, relationships_data
    )

    st.subheader("Subgrafo retornado pela recuperação")
    col1, col2, col3 = st.columns(3)
    col1.metric("Nós retornados", len(graph_nodes))
    col2.metric("Relacionamentos retornados", len(graph_edges))
    col3.metric("Menções candidatas", candidate_count)

    agraph(
        nodes=graph_nodes,
        edges=graph_edges,
        config=Config(width="100%", height=500, directed=True, physics=True, hierarchical=False),
    )

    node_legend = " · ".join(
        f"{label} ({cor})" for label, cor in ui_helpers.NODE_LEGEND_ITEMS
    )
    st.caption(
        "Arestas — Azul contínuo: relação estrutural do grafo. "
        "Vermelho tracejado: MENCIONA (CANDIDATA), menção textual que exige validação. "
        "As arestas exibidas são somente as retornadas pelo Neo4j."
    )
    st.caption(f"Cores dos nós — {node_legend}.")


def render_payload(payload: dict) -> None:
    """Renderiza avisos, resposta, fontes, consulta Cypher e subgrafo."""
    for warning in payload.get("warnings", []):
        st.warning(warning)

    if payload.get("abstained"):
        st.error(payload.get("answer", "O sistema se absteve de responder."))
    else:
        st.success(payload.get("answer", "Busca concluída."))

    _render_sources(payload.get("sources", []))

    if payload.get("cypher"):
        with st.expander("Consulta Cypher"):
            st.code(payload["cypher"], language="cypher")

    relevance = payload.get("retrieval_relevance")
    if relevance is not None:
        st.caption(
            f"Relevância normalizada da recuperação: {relevance:.3f}. "
            "Esse valor não representa probabilidade de fraude ou irregularidade."
        )

    _render_graph_section(
        payload.get("nodes", []),
        payload.get("relationships", []),
    )


def _render_neo4j_status() -> None:
    with st.expander("Status da conexão Neo4j"):
        status = ui_helpers.check_neo4j_status(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            user=os.getenv("NEO4J_USER", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD"),
            database=os.getenv("NEO4J_DATABASE") or None,
        )
        state = status["state"]
        if state == "missing_password":
            st.warning(status["message"])
        elif state == "connected":
            col1, col2 = st.columns(2)
            col1.metric("Nós", status["nodes"])
            col2.metric("Relacionamentos", status["relationships"])
        else:
            st.error(status["message"])


def main() -> None:
    st.set_page_config(page_title="FiscalGraph BR", page_icon="🔎", layout="wide")
    st.title("FiscalGraph BR")
    st.caption("Consulta explicável de informações públicas de compliance empresarial.")

    st.info(
        "Protótipo acadêmico. Registros públicos, coincidências cadastrais e menções textuais "
        "não comprovam fraude, irregularidade atual ou responsabilidade de terceiros."
    )

    _render_neo4j_status()

    st.sidebar.header("Modo de execução")
    mode = st.sidebar.radio(
        "Selecione o modo",
        ["Consulta real (Neo4j)", "Demonstração (Mock)"],
        help="A demonstração usa fixtures sintéticas e não executa recuperação.",
    )
    top_k = st.sidebar.slider("Quantidade de evidências (top_k)", min_value=1, max_value=10, value=5)
    enable_llm_cypher = st.sidebar.checkbox(
        "Habilitar consulta Cypher gerada por LLM",
        value=False,
        help="Requer LLM_CYPHER_ENABLED=true e credenciais configuradas no ambiente.",
    )
    if not llm_cypher.cypher_generation_is_configured():
        st.sidebar.caption("Cypher via LLM está indisponível até ser habilitado explicitamente no ambiente.")
    mock_scenario = st.sidebar.radio(
        "Cenário de demonstração",
        ["Sucesso (grafo e fontes)", "Abstenção (sem conclusão)"],
        disabled=(mode != "Demonstração (Mock)"),
    )
    st.sidebar.caption(
        "Limites: recorte canônico de 18 empresas; MENCIONA (CANDIDATA) não implica vínculo jurídico."
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
            st.caption(
                "Modo demonstração: os dados exibidos são sintéticos e independem da pergunta digitada."
            )
            payload = mock_service.get_mock_response(
                "sucesso" if mock_scenario.startswith("Sucesso") else "abstencao"
            )
            render_payload(payload)
        else:
            try:
                with st.spinner("Consultando os índices vetorial e full-text e expandindo o grafo..."):
                    retriever = get_retriever()
                    payload = orchestrator.answer_question(
                        question, top_k=top_k, retriever=retriever
                    )
                render_payload(payload)
            except (RuntimeError, ValueError, OSError) as exc:
                st.error("Não foi possível executar a consulta real.")
                with st.expander("Detalhes técnicos"):
                    st.code(ui_helpers.sanitize_error_message(str(exc)))
            except Exception as exc:
                st.error("Ocorreu um erro inesperado durante a consulta.")
                with st.expander("Detalhes técnicos"):
                    st.code(
                        ui_helpers.sanitize_error_message(f"{type(exc).__name__}: {exc}")
                    )
    else:
        st.caption("Escolha o modo, informe uma pergunta e pressione Pesquisar.")

    st.divider()
    st.subheader("Consulta estruturada Cypher via LLM")
    st.caption(
        "Recurso experimental e opcional. A pergunta e o schema são enviados ao provedor LLM; "
        "nenhum registro recuperado é enviado. A consulta é validada, limitada e executada somente para leitura."
    )
    with st.form("llm_cypher_form"):
        cypher_question = st.text_input(
            "Pergunta para gerar Cypher",
            placeholder="Ex.: Liste empresas e estabelecimentos localizados no Ceará.",
            disabled=not enable_llm_cypher or mode != "Consulta real (Neo4j)",
        )
        cypher_submitted = st.form_submit_button(
            "Gerar e executar consulta somente leitura",
            disabled=not enable_llm_cypher or mode != "Consulta real (Neo4j)",
        )

    if cypher_submitted:
        if not cypher_question.strip():
            st.warning("Digite uma pergunta para gerar a consulta.")
        elif not llm_cypher.cypher_generation_is_configured():
            st.error("O recurso exige LLM_CYPHER_ENABLED=true e as credenciais do provedor.")
        else:
            try:
                with st.spinner("Gerando, validando e executando consulta Cypher..."):
                    active_retriever = get_retriever()
                    generated = llm_cypher.generate_cypher(cypher_question)
                    rows = llm_cypher.execute_read_only_cypher(
                        active_retriever.driver,
                        generated["cypher"],
                        database=active_retriever.database,
                    )
                st.code(generated["cypher"], language="cypher")
                if generated.get("rationale"):
                    st.caption(generated["rationale"])
                st.metric("Registros retornados", len(rows))
                st.json(rows)
                st.caption("Consulta aprovada pelo validador local e executada sem cláusulas de escrita.")
            except Exception as exc:
                st.error("Não foi possível gerar ou executar a consulta Cypher.")
                with st.expander("Detalhes técnicos"):
                    st.code(ui_helpers.sanitize_error_message(f"{type(exc).__name__}: {exc}"))


if __name__ == "__main__":
    main()
