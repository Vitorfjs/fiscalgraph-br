"""Normaliza fontes do contrato final e das fixtures antigas do Dev6."""

from typing import Any, Dict


def normalize_source(source: Dict[str, Any]) -> Dict[str, Any]:
    """Retorna o formato canônico de fonte usado pelo renderer."""
    record_id = source.get("registro_id")
    source_id = (
        source.get("id")
        or record_id
        or source.get("fonte_id")
        or source.get("trecho_id")
    )
    label = source.get("label") or ("Sancao" if record_id else "Trecho")
    return {
        "id": source_id,
        "label": label,
        "url": source.get("url") or source.get("url_fonte"),
        "excerpt": source.get("excerpt") or source.get("texto") or "",
    }
