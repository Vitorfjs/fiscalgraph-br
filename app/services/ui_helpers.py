"""Funções auxiliares de UI, checagem de status Neo4j e estilização de grafo."""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable
from streamlit_agraph import Edge, Node

DEFAULT_NODE_COLOR = "#7F7F7F"
NODE_COLORS: Dict[str, str] = {
    "Empresa": "#1F77B4",
    "Estabelecimento": "#2CA02C",
    "Socio": "#9467BD",
    "CNAE": "#8C564B",
    "Sancao": "#D62728",
    "Fonte": "#17BECF",
    "Trecho": "#FF7F0E",
}

NODE_LEGEND_ITEMS: Tuple[Tuple[str, str], ...] = (
    ("Empresa", "Azul"),
    ("Estabelecimento", "Verde"),
    ("Socio", "Roxo"),
    ("CNAE", "Marrom"),
    ("Sancao", "Vermelho escuro"),
    ("Fonte", "Ciano"),
    ("Trecho", "Laranja"),
)

_PLACEHOLDER_PASSWORD = "change_this_password_before_starting"


def sanitize_error_message(message: str, secrets: Optional[Iterable[str]] = None) -> str:
    """Mascara eventuais valores sensíveis antes de exibir detalhes técnicos na interface."""
    sanitized = str(message)
    candidate_secrets = (
        list(secrets)
        if secrets is not None
        else [os.getenv("NEO4J_PASSWORD", ""), os.getenv("LLM_API_KEY", "")]
    )
    for secret in candidate_secrets:
        if secret:
            sanitized = sanitized.replace(secret, "***")
    return sanitized


def check_neo4j_status(
    uri: str,
    user: str,
    password: Optional[str],
    database: Optional[str] = None,
    timeout_seconds: float = 3.0,
) -> Dict[str, Any]:
    """Verifica conectividade e volumetria básica do Neo4j usando sintaxe Cypher 5."""
    if not password or password == _PLACEHOLDER_PASSWORD:
        return {
            "state": "missing_password",
            "message": "Configure NEO4J_PASSWORD no arquivo .env para habilitar a consulta real.",
        }

    try:
        with GraphDatabase.driver(uri, auth=(user, password), connection_timeout=timeout_seconds) as driver:
            driver.verify_connectivity()
            with driver.session(database=database or None) as session:
                record = session.run(
                    "CALL () { MATCH (n) RETURN count(n) AS nodes } "
                    "CALL () { MATCH ()-[r]->() RETURN count(r) AS relationships } "
                    "RETURN nodes, relationships"
                ).single()
        return {
            "state": "connected",
            "nodes": record["nodes"] if record else 0,
            "relationships": record["relationships"] if record else 0,
            "message": "Conexão ativa com o Neo4j.",
        }
    except AuthError:
        return {
            "state": "auth_error",
            "message": "Falha de autenticação no Neo4j. Confira NEO4J_USER e NEO4J_PASSWORD.",
        }
    except ServiceUnavailable:
        return {
            "state": "unavailable",
            "message": "Neo4j indisponível. Inicie o serviço e confira NEO4J_URI.",
        }


def _short_node_title(label: str, properties: Dict[str, Any]) -> str:
    """Extrai um rótulo curto legível preservando o tipo do nó."""
    for key in ("razao_social", "nome_socio", "nome", "cnpj", "codigo", "registro_id", "trecho_id", "fonte_id", "sancao_id"):
        value = properties.get(key)
        if value:
            text = str(value).strip()
            if len(text) > 28:
                text = text[:25] + "..."
            return f"{label}: {text}"
    return label


def build_graph_elements(
    nodes_data: List[Dict[str, Any]],
    relationships_data: List[Dict[str, Any]],
) -> Tuple[List[Node], List[Edge], int]:
    """Constrói nós e arestas do `streamlit-agraph` destacando menções candidatas."""
    graph_nodes: List[Node] = []
    graph_edges: List[Edge] = []
    node_ids = {node_data.get("id") for node_data in nodes_data if node_data.get("id")}

    for node_data in nodes_data:
        node_id = node_data["id"]
        label = node_data.get("label", "Node")
        properties = node_data.get("properties") or {}
        tooltip_lines = [f"Tipo: {label}"]
        tooltip_lines.extend(f"{key}: {value}" for key, value in properties.items())
        graph_nodes.append(
            Node(
                id=node_id,
                label=_short_node_title(label, properties),
                title="\n".join(tooltip_lines),
                color=NODE_COLORS.get(label, DEFAULT_NODE_COLOR),
                size=25,
            )
        )

    candidate_count = 0
    for relationship in relationships_data:
        source = relationship.get("source")
        target = relationship.get("target")
        if source not in node_ids or target not in node_ids:
            continue
        properties = relationship.get("properties") or {}
        relation_type = relationship.get("type", "UNKNOWN")
        is_candidate = relation_type in {"MENCIONA", "MENCAO_NOME"} and properties.get("status") == "CANDIDATA"
        if is_candidate:
            candidate_count += 1
        edge_label = f"{relation_type} (CANDIDATA)" if is_candidate else relation_type
        graph_edges.append(
            Edge(
                source=source,
                target=target,
                label=edge_label,
                color="#FF4B4B" if is_candidate else "#4A90E2",
                dashes=is_candidate,
            )
        )

    return graph_nodes, graph_edges, candidate_count
