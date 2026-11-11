"""Validadores executáveis do contrato do dev5 (seção 7 de ``docs/recuperacao-hibrida.md``).

Consumidores (dev1, dev6) podem chamar estes validadores nos próprios testes para confirmar que
recebem respostas compatíveis. Lista vazia significa resposta válida.

- ``validate_retrieval_response``: saída de ``retrieve_context``;
- ``validate_company_paths_response``: saída de ``company_paths``;
- ``example_final_response``: exemplo de referência do mapeamento para a resposta final do dev1
  (seção 7.3). A resposta final é responsabilidade do dev1; o ``answer`` do exemplo é um marcador.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Sequence

TOP_LEVEL_FIELDS = {
    "query": str,
    "retrieval_mode": str,
    "chunks": list,
    "nodes": list,
    "relationships": list,
    "cypher": str,
    "warnings": list,
    "parameters": dict,
}
OPTIONAL_TEXT_FIELDS = ("registro_id", "fonte_id", "url_fonte")
RANK_SCORE_FIELDS = (("vector_rank", "vector_score", "vector"), ("fulltext_rank", "fulltext_score", "fulltext"))
SEARCH_NAMES = ("vector", "fulltext")
SEARCH_STATES = ("com_resultados", "sem_resultados", "indisponivel", "nao_executada")
FORBIDDEN_NODE_PROPERTIES = ("embedding", "texto", "mencoes_json")
MENCIONA_PROPERTIES = ("status", "inicio", "fim", "metodo")
PATH_KINDS = ("societario", "mencao_candidata", "atividade_cnae", "estrutural")


def _is_rank(value: Any) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 1)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _graph_problems(nodes: Sequence[Any], relationships: Sequence[Any]) -> List[str]:
    """Nós com id único e propriedades mínimas; arestas apontando para nós existentes."""
    problems: List[str] = []
    node_ids = set()
    for index, node in enumerate(nodes):
        where = f"nodes[{index}]"
        if not isinstance(node, dict):
            problems.append(f"{where} não é dict")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            problems.append(f"{where}.id deve ser texto não vazio")
        elif node_id in node_ids:
            problems.append(f"{where}.id repetido: {node_id}")
        else:
            node_ids.add(node_id)
        if not isinstance(node.get("label"), str) or not node.get("label"):
            problems.append(f"{where}.label deve ser texto não vazio")
        properties = node.get("properties")
        if not isinstance(properties, dict):
            problems.append(f"{where}.properties deve ser dict")
        else:
            leaked = [key for key in FORBIDDEN_NODE_PROPERTIES if key in properties]
            if leaked:
                problems.append(f"{where}.properties não pode conter {leaked} (vetor/texto duplicado)")

    for index, rel in enumerate(relationships):
        where = f"relationships[{index}]"
        if not isinstance(rel, dict):
            problems.append(f"{where} não é dict")
            continue
        for end in ("source", "target"):
            if rel.get(end) not in node_ids:
                problems.append(f"{where}.{end} não aponta para um nó de 'nodes': {rel.get(end)!r}")
        if not isinstance(rel.get("type"), str) or not rel.get("type"):
            problems.append(f"{where}.type deve ser texto não vazio")
        properties = rel.get("properties")
        if not isinstance(properties, dict):
            problems.append(f"{where}.properties deve ser dict")
        elif rel.get("type") == "MENCIONA":
            missing = [key for key in MENCIONA_PROPERTIES if key not in properties]
            if missing:
                problems.append(f"{where} (MENCIONA) sem as propriedades {missing}")
    return problems


def _json_problems(result: Any) -> List[str]:
    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        return [f"resposta não serializável em JSON: {exc}"]
    return []


def _parameters_problems(parameters: Dict[str, Any]) -> List[str]:
    problems = []
    active = parameters.get("active_searches")
    if not isinstance(active, list) or any(name not in SEARCH_NAMES for name in active):
        problems.append(f"parameters.active_searches deve ser lista com valores de {list(SEARCH_NAMES)}")
    status = parameters.get("search_status")
    if not isinstance(status, dict) or set(status) != set(SEARCH_NAMES) or any(
            state not in SEARCH_STATES for state in status.values()):
        problems.append(f"parameters.search_status deve mapear {list(SEARCH_NAMES)} para {list(SEARCH_STATES)}")
    elif isinstance(active, list) and sorted(active) != sorted(
            name for name, state in status.items() if state == "com_resultados"):
        problems.append("parameters.active_searches não corresponde a search_status")
    for key in ("rrf_k", "rrf_max_score"):
        if key in parameters and not (_is_number(parameters[key]) and parameters[key] > 0):
            problems.append(f"parameters.{key} deve ser número positivo")
    return problems


def validate_retrieval_response(result: Any) -> List[str]:
    """Devolve a lista de violações do contrato de ``retrieve_context`` encontradas em ``result``."""
    if not isinstance(result, dict):
        return ["a resposta precisa ser um dict"]
    problems = [
        f"campo {key!r} ausente ou não é {kind.__name__}"
        for key, kind in TOP_LEVEL_FIELDS.items()
        if not isinstance(result.get(key), kind)
    ]
    if problems:
        return problems

    parameters = result["parameters"]
    problems += _parameters_problems(parameters)
    active = parameters.get("active_searches") if isinstance(parameters.get("active_searches"), list) else []
    rrf_k = parameters.get("rrf_k") if _is_number(parameters.get("rrf_k")) else None
    rrf_max = parameters.get("rrf_max_score") if _is_number(parameters.get("rrf_max_score")) else None
    query_identifiers = parameters.get("query_identifiers")
    if not isinstance(query_identifiers, list) or not all(isinstance(i, str) for i in query_identifiers):
        problems.append("parameters.query_identifiers deve ser lista de textos")
        query_identifiers = []

    if result["retrieval_mode"] != "hybrid":
        problems.append(f"retrieval_mode deveria ser 'hybrid', veio {result['retrieval_mode']!r}")
    if not all(isinstance(warning, str) for warning in result["warnings"]):
        problems.append("warnings deve conter apenas textos")

    scores = []
    for index, chunk in enumerate(result["chunks"]):
        where = f"chunks[{index}]"
        if not isinstance(chunk, dict):
            problems.append(f"{where} não é dict")
            continue
        if not isinstance(chunk.get("trecho_id"), str) or not chunk["trecho_id"]:
            problems.append(f"{where}.trecho_id deve ser texto não vazio")
        if not isinstance(chunk.get("texto"), str):
            problems.append(f"{where}.texto deve ser texto")
        for key in OPTIONAL_TEXT_FIELDS:
            if key not in chunk or not (chunk[key] is None or isinstance(chunk[key], str)):
                problems.append(f"{where}.{key} deve existir e ser texto ou None")
        for rank_key, score_key, search in RANK_SCORE_FIELDS:
            rank, score = chunk.get(rank_key), chunk.get(score_key)
            if rank_key not in chunk or not _is_rank(rank):
                problems.append(f"{where}.{rank_key} deve existir e ser inteiro >= 1 ou None")
            if score_key not in chunk or not (score is None or _is_number(score)):
                problems.append(f"{where}.{score_key} deve existir e ser número finito ou None")
            if (rank is None) != (score is None):
                problems.append(f"{where}.{rank_key} e {score_key} devem ser ambos None ou ambos preenchidos")
            if rank is not None and search not in active:
                problems.append(f"{where}.{rank_key} preenchido, mas '{search}' não está em active_searches")
        if chunk.get("vector_rank") is None and chunk.get("fulltext_rank") is None:
            problems.append(f"{where} não tem rank em nenhuma das buscas")
        paths = chunk.get("graph_paths")
        if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
            problems.append(f"{where}.graph_paths deve ser lista de textos")
        matches = chunk.get("identifier_matches")
        if not isinstance(matches, list) or not all(isinstance(m, str) for m in matches):
            problems.append(f"{where}.identifier_matches deve ser lista de textos")
        elif any(m not in query_identifiers for m in matches):
            problems.append(f"{where}.identifier_matches cita identificador ausente de parameters.query_identifiers")
        rrf = chunk.get("rrf_score")
        if not isinstance(rrf, float) or not math.isfinite(rrf) or rrf <= 0:
            problems.append(f"{where}.rrf_score deve ser float finito e positivo")
            continue
        scores.append(rrf)
        if rrf_max is not None and rrf > rrf_max + 1e-12:
            problems.append(f"{where}.rrf_score acima de parameters.rrf_max_score")
        if rrf_k is not None and all(_is_rank(chunk.get(key)) for key, _, _ in RANK_SCORE_FIELDS):
            expected = sum(1.0 / (rrf_k + chunk[key]) for key, _, _ in RANK_SCORE_FIELDS if chunk.get(key))
            if abs(expected - rrf) > 1e-9:
                problems.append(f"{where}.rrf_score não corresponde aos ranks (esperado {expected:.6f})")
    if scores != sorted(scores, reverse=True):
        problems.append("chunks fora da ordem decrescente de rrf_score")

    problems += _graph_problems(result["nodes"], result["relationships"])
    if not result["chunks"] and not result["warnings"]:
        problems.append("sem evidência e sem aviso: o contrato exige aviso claro")
    return problems + _json_problems(result)


def validate_company_paths_response(result: Any) -> List[str]:
    """Devolve a lista de violações do contrato de ``company_paths``."""
    if not isinstance(result, dict):
        return ["a resposta precisa ser um dict"]
    expected = {"empresas": list, "max_hops": int, "paths": list, "nodes": list,
                "relationships": list, "cypher": str, "warnings": list}
    problems = [f"campo {key!r} ausente ou não é {kind.__name__}"
                for key, kind in expected.items() if not isinstance(result.get(key), kind)]
    if problems:
        return problems
    node_ids = {node.get("id") for node in result["nodes"] if isinstance(node, dict)}
    for index, path in enumerate(result["paths"]):
        where = f"paths[{index}]"
        if not isinstance(path, dict):
            problems.append(f"{where} não é dict")
            continue
        if path.get("kind") not in PATH_KINDS:
            problems.append(f"{where}.kind deve ser um de {list(PATH_KINDS)}")
        ids, types = path.get("nodes"), path.get("relationship_types")
        if not isinstance(ids, list) or not isinstance(types, list) or len(ids) != len(types) + 1:
            problems.append(f"{where}: nodes deve ter um item a mais que relationship_types")
        elif any(node_id not in node_ids for node_id in ids):
            problems.append(f"{where}.nodes cita nó ausente de 'nodes'")
        if path.get("length") != (len(types) if isinstance(types, list) else None):
            problems.append(f"{where}.length deve ser igual ao número de relacionamentos")
        if not isinstance(path.get("text"), str) or not path.get("text"):
            problems.append(f"{where}.text deve ser texto não vazio")
    if not all(isinstance(warning, str) for warning in result["warnings"]):
        problems.append("warnings deve conter apenas textos")
    if not result["paths"] and not result["warnings"]:
        problems.append("sem caminho e sem aviso")
    problems += _graph_problems(result["nodes"], result["relationships"])
    return problems + _json_problems(result)


def example_final_response(context: Dict[str, Any], answer: str = "") -> Dict[str, Any]:
    """Exemplo do mapeamento da seção 7.3: saída do dev5 → resposta final (seção 4 do contrato original).

    Usa apenas campos de ``retrieve_context``, sem consulta extra ao banco. Não decide abstenção
    por limiar: ``abstained`` só é ``True`` quando não há trecho; o dev1 define a regra final.
    """
    chunks = context["chunks"]
    sources, seen = [], set()
    for chunk in chunks:
        source_id = chunk["registro_id"] or chunk["trecho_id"]
        if source_id not in seen:
            seen.add(source_id)
            sources.append({
                "id": source_id,
                "label": "Sancao" if chunk["registro_id"] else "Trecho",
                "url": chunk["url_fonte"],
                "excerpt": chunk["texto"],
            })
    max_score = context["parameters"]["rrf_max_score"]
    return {
        "answer": answer,
        "cypher": context["cypher"],
        "sources": sources,
        "nodes": context["nodes"],
        "relationships": context["relationships"],
        "retrieval_relevance": chunks[0]["rrf_score"] / max_score if chunks else None,
        "abstained": not chunks,
        "warnings": list(context["warnings"]),
    }
