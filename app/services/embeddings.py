"""Configuração única de embeddings e do índice vetorial de ``Trecho``.

O gerador (``scripts/generate_embeddings.py``) e o serviço de recuperação
(``app/services/retrieval.py``) importam estas constantes, para que modelo, dimensão e
nome do índice não divirjam. Alterar modelo ou dimensão exige reprocessar todos os
embeddings e recriar o índice, em ajuste coordenado com dev3.
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSIONS = 384
VECTOR_SIMILARITY = "cosine"
VECTOR_INDEX = "trecho_embedding_vector"
VECTOR_LABEL = "Trecho"
VECTOR_PROPERTY = "embedding"

# Mesmo comando versionado em cypher/04_indice_vetorial_trecho.cypher.
CREATE_VECTOR_INDEX = (
    f"CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS\n"
    f"FOR (t:{VECTOR_LABEL}) ON (t.{VECTOR_PROPERTY})\n"
    "OPTIONS {indexConfig: {\n"
    f"  `vector.dimensions`: {EMBEDDING_DIMENSIONS},\n"
    f"  `vector.similarity_function`: '{VECTOR_SIMILARITY}'\n"
    "}}"
)

SHOW_VECTOR_INDEX = """
SHOW INDEXES
YIELD name, type, labelsOrTypes, properties, options, state
WHERE name = $name
RETURN name, type, labelsOrTypes, properties, options, state
"""


class SentenceEncoder:
    """Envoltório do Sentence Transformers que garante vetores normalizados de 384 dimensões."""

    def __init__(self, model_name: str = MODEL_NAME, model: Any = None):
        if model is None:
            # Import tardio: torch/sentence-transformers só são carregados quando necessários.
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
        dimension = model.get_sentence_embedding_dimension()
        if dimension != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"O modelo {model_name} produz {dimension} dimensões; o índice "
                f"{VECTOR_INDEX} espera {EMBEDDING_DIMENSIONS}."
            )
        self.model = model
        self.model_name = model_name
        self.max_seq_length: Optional[int] = getattr(model, "max_seq_length", None)

    def encode(self, texts: Sequence[str], batch_size: int = 32) -> List[List[float]]:
        vectors = self.model.encode(
            list(texts),
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        result = [list(map(float, vector)) for vector in vectors]
        for vector in result:
            validate_vector(vector)
        return result


def validate_vector(vector: Sequence[float]) -> None:
    """Recusa vetores que o índice não aceitaria ou que distorceriam o cosseno."""
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Vetor com {len(vector)} dimensões; esperado {EMBEDDING_DIMENSIONS}.")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("Vetor contém NaN ou infinito.")


def vector_index_problems(row: Optional[dict]) -> List[str]:
    """Compara a linha de ``SHOW INDEXES`` com a configuração esperada. Lista vazia = ok."""
    if row is None:
        return [f"Índice {VECTOR_INDEX} não existe."]
    problems = []
    if row.get("type") != "VECTOR":
        problems.append(f"Índice {VECTOR_INDEX} tem tipo {row.get('type')}, esperado VECTOR.")
    if list(row.get("labelsOrTypes") or []) != [VECTOR_LABEL]:
        problems.append(f"Índice {VECTOR_INDEX} cobre {row.get('labelsOrTypes')}, esperado [{VECTOR_LABEL}].")
    if list(row.get("properties") or []) != [VECTOR_PROPERTY]:
        problems.append(f"Índice {VECTOR_INDEX} cobre {row.get('properties')}, esperado [{VECTOR_PROPERTY}].")
    config = (row.get("options") or {}).get("indexConfig") or {}
    dimensions = config.get("vector.dimensions")
    if dimensions != EMBEDDING_DIMENSIONS:
        problems.append(f"Índice {VECTOR_INDEX} tem {dimensions} dimensões, esperado {EMBEDDING_DIMENSIONS}.")
    similarity = str(config.get("vector.similarity_function", "")).lower()
    if similarity != VECTOR_SIMILARITY:
        problems.append(f"Índice {VECTOR_INDEX} usa similaridade {similarity!r}, esperado {VECTOR_SIMILARITY!r}.")
    return problems
