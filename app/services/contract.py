"""Validador executável do contrato de ``retrieve_context`` (seção 3 do contrato de dados).

Consumidores (dev1, dev6) podem chamar ``validate_retrieval_response`` nos próprios testes para
confirmar que recebem uma resposta compatível. Lista vazia significa resposta válida.

Campos extras (``vector_score``, ``fulltext_score``, ``graph_paths``, ``parameters``) são
permitidos: o contrato define o mínimo, e consumidores devem ignorar chaves que não usam.
"""
from __future__ import annotations

import json
from typing import Any, List

TOP_LEVEL_FIELDS = {
    "query": str,
    "retrieval_mode": str,
    "chunks": list,
    "nodes": list,
    "relationships": list,
    "cypher": str,
    "warnings": list,
}
OPTIONAL_TEXT_FIELDS = ("registro_id", "fonte_id", "url_fonte")
RANK_FIELDS = ("vector_rank", "fulltext_rank")


def _is_rank(value: Any) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 1)


def validate_retrieval_response(result: Any) -> List[str]:
    """Devolve a lista de violações do contrato encontradas em ``result``."""
    if not isinstance(result, dict):
        return ["a resposta precisa ser um dict"]
    problems = [
        f"campo {key!r} ausente ou não é {kind.__name__}"
        for key, kind in TOP_LEVEL_FIELDS.items()
        if not isinstance(result.get(key), kind)
    ]
    if problems:
        return problems

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
        for key in RANK_FIELDS:
            if key not in chunk or not _is_rank(chunk[key]):
                problems.append(f"{where}.{key} deve existir e ser inteiro >= 1 ou None")
        if chunk.get("vector_rank") is None and chunk.get("fulltext_rank") is None:
            problems.append(f"{where} não tem rank em nenhuma das buscas")
        score = chunk.get("rrf_score")
        if not isinstance(score, float) or score <= 0:
            problems.append(f"{where}.rrf_score deve ser float positivo")
        else:
            scores.append(score)
    if scores != sorted(scores, reverse=True):
        problems.append("chunks fora da ordem decrescente de rrf_score")

    node_ids = set()
    for index, node in enumerate(result["nodes"]):
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
        if not isinstance(node.get("properties"), dict):
            problems.append(f"{where}.properties deve ser dict")

    for index, rel in enumerate(result["relationships"]):
        where = f"relationships[{index}]"
        if not isinstance(rel, dict):
            problems.append(f"{where} não é dict")
            continue
        for end in ("source", "target"):
            if rel.get(end) not in node_ids:
                problems.append(f"{where}.{end} não aponta para um nó de 'nodes': {rel.get(end)!r}")
        if not isinstance(rel.get("type"), str) or not rel.get("type"):
            problems.append(f"{where}.type deve ser texto não vazio")
        if not isinstance(rel.get("properties"), dict):
            problems.append(f"{where}.properties deve ser dict")

    if not result["chunks"] and not result["warnings"]:
        problems.append("sem evidência e sem aviso: o contrato exige aviso claro")

    try:
        json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        problems.append(f"resposta não serializável em JSON: {exc}")
    return problems
