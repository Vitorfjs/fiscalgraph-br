"""Fusão de rankings por Reciprocal Rank Fusion (RRF).

RRF (Cormack, Clarke e Büttcher, 2009) combina listas ordenadas usando somente a
posição de cada item:

    rrf_score(d) = Σ_listas 1 / (k + rank_lista(d))

Como apenas a posição importa, os scores brutos da busca vetorial (similaridade de
cosseno) e da busca full-text (relevância Lucene) — que estão em escalas diferentes —
nunca são somados nem comparados entre si.

O ``rrf_score`` mede relevância de recuperação. Não é probabilidade de irregularidade,
fraude ou responsabilidade.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

DEFAULT_RRF_K = 60


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k precisa ser um inteiro maior ou igual a 1")


def reciprocal_rank_fusion(
    vector_ids: Iterable[Optional[str]],
    fulltext_ids: Iterable[Optional[str]],
    k: int = DEFAULT_RRF_K,
) -> List[dict]:
    """Funde as listas vetorial e full-text de ``trecho_id`` por RRF.

    Regras:
    - ``rank`` é a posição 1-based do identificador na sua lista, contando só valores
      válidos e distintos (``None`` é ignorado; repetição conta apenas a 1ª ocorrência);
    - cada item recebe ``vector_rank`` e ``fulltext_rank`` (``None`` quando ausente);
    - a saída é ordenada por ``rrf_score`` decrescente; empates preservam a ordem em que
      o item apareceu pela primeira vez (lista vetorial primeiro, depois full-text).
    """
    _validate_k(k)
    scores: Dict[str, float] = {}
    ranks: Dict[str, Dict[str, Optional[int]]] = {}

    for rank_key, identifiers in (("vector_rank", vector_ids), ("fulltext_rank", fulltext_ids)):
        rank = 0
        seen = set()
        for identifier in identifiers:
            if identifier is None or identifier in seen:
                continue
            seen.add(identifier)
            rank += 1
            if identifier not in scores:
                scores[identifier] = 0.0
                ranks[identifier] = {"vector_rank": None, "fulltext_rank": None}
            scores[identifier] += 1.0 / (k + rank)
            ranks[identifier][rank_key] = rank

    fused = [
        {"trecho_id": identifier, "rrf_score": score, **ranks[identifier]}
        for identifier, score in scores.items()
    ]
    # sorted() é estável: empates mantêm a ordem de inserção descrita na docstring.
    return sorted(fused, key=lambda item: item["rrf_score"], reverse=True)
