"""Converte a resposta de recuperação do Dev5 para o contrato final da aplicação."""

from typing import Any, Dict, Iterable, List, Optional



def evidence_confidence(context: Dict[str, Any]) -> Dict[str, Any]:
    """Deriva nível heurístico de sustentação documental; não é score probabilístico."""
    chunks = context.get("chunks") or []
    if not chunks:
        return {
            "level": "Sem evidências",
            "basis": ["Nenhum trecho foi recuperado para sustentar a resposta."],
            "disclaimer": (
                "Nível documental, não probabilidade de fraude ou de responsabilidade jurídica."
            ),
        }

    parameters = context.get("parameters") or {}
    records = {
        chunk.get("registro_id") or chunk.get("trecho_id")
        for chunk in chunks
        if chunk.get("registro_id") or chunk.get("trecho_id")
    }
    sources = {chunk.get("fonte_id") for chunk in chunks if chunk.get("fonte_id")}
    search_status = parameters.get("search_status") or {}
    executed_searches = {
        name for name, state in search_status.items()
        if state in {"com_resultados", "sem_resultados"}
    }
    has_exact_identifier = any(chunk.get("identifier_matches") for chunk in chunks)
    structural_types = {
        "APLICADA_A", "PARTICIPA_DE", "POSSUI_ESTABELECIMENTO", "EXERCE_CNAE"
    }
    relationship_types = {
        relationship.get("type")
        for relationship in context.get("relationships", [])
        if isinstance(relationship, dict)
    }
    # Caminhos de proveniência ou menções candidatas não contam como corroboração
    # estrutural; apenas relações tipadas do domínio entram neste sinal.
    has_structured_path = bool(structural_types & relationship_types)

    signals: List[str] = []
    if len(records) >= 3:
        signals.append(f"{len(records)} registros distintos")
    if len(sources) >= 2:
        signals.append(f"{len(sources)} fontes distintas")
    if {"vector", "fulltext"}.issubset(executed_searches):
        signals.append("buscas vetorial e full-text executadas")
    if has_exact_identifier:
        signals.append("correspondência literal de identificador")
    if has_structured_path:
        signals.append("caminho estruturado no subgrafo")

    partial_search = any(
        search_status.get(name) not in {"com_resultados", "sem_resultados"}
        for name in ("vector", "fulltext")
    )
    score = len(signals)
    if score >= 4:
        level = "Alta"
    elif score >= 2:
        level = "Moderada"
    else:
        level = "Baixa"

    if partial_search:
        if level == "Alta":
            level = "Moderada"
        elif level == "Moderada":
            level = "Baixa"
        signals.append("modalidade de busca indisponível ou não executada; nível rebaixado")

    if not signals:
        signals.append("poucos sinais independentes de corroboração no recorte")

    return {
        "level": level,
        "basis": signals,
        "disclaimer": (
            "Nível heurístico de sustentação documental no recorte consultado. "
            "Não é confiança estatística, probabilidade de fraude, prova de irregularidade "
            "ou conclusão sobre responsabilidade jurídica."
        ),
    }


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

    confidence = evidence_confidence(context)
    return {
        "answer": answer,
        "cypher": context.get("cypher", ""),
        "confidence_level": confidence["level"],
        "confidence_basis": confidence["basis"],
        "confidence_disclaimer": confidence["disclaimer"],
        "sources": sources,
        "nodes": list(context.get("nodes", [])),
        "relationships": list(context.get("relationships", [])),
        "retrieval_relevance": relevance,
        "abstained": (not chunks) if abstained is None else bool(abstained),
        "warnings": warnings,
    }
