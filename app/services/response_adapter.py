"""Converte a resposta de recuperação do Dev5 para o contrato final da aplicação."""

from typing import Any, Dict, Iterable, Optional


def build_final_response(
    context: Dict[str, Any],
    answer: str,
    abstained: Optional[bool] = None,
    additional_warnings: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Mapeia chunks para fontes e preserva grafo, consulta e avisos."""
    chunks = context.get("chunks", [])
    sources = []
    seen = set()

    for chunk in chunks:
        record_id = chunk.get("registro_id")
        source_id = record_id or chunk.get("trecho_id")
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        sources.append({
            "id": source_id,
            "label": "Sancao" if record_id else "Trecho",
            "url": chunk.get("url_fonte"),
            "excerpt": chunk.get("texto", ""),
        })

    parameters = context.get("parameters", {})
    max_score = parameters.get("rrf_max_score")
    relevance = None
    if chunks and max_score:
        relevance = chunks[0].get("rrf_score", 0) / max_score

    warnings = list(context.get("warnings", []))
    for warning in additional_warnings or []:
        if warning not in warnings:
            warnings.append(warning)

    return {
        "answer": answer,
        "cypher": context.get("cypher", ""),
        "sources": sources,
        "nodes": list(context.get("nodes", [])),
        "relationships": list(context.get("relationships", [])),
        "retrieval_relevance": relevance,
        "abstained": (not chunks) if abstained is None else bool(abstained),
        "warnings": warnings,
    }
