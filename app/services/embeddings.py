"""Configuração única de embeddings e do índice vetorial de ``Trecho``.

O gerador (``scripts/generate_embeddings.py``) e o serviço de recuperação
(``app/services/retrieval.py``) importam estas constantes e o mesmo ``SentenceEncoder``, para
que modelo, dimensão, estratégia de segmentação e índice não divirjam entre documentos e
perguntas. Alterar modelo ou dimensão exige reprocessar todos os embeddings e recriar o índice,
em ajuste coordenado com dev3.

Estratégia (seção 4 de ``docs/recuperacao-hibrida.md``): o texto é tokenizado com o tokenizador
do próprio modelo e dividido em janelas de ``WINDOW_TOKENS`` tokens com ``WINDOW_OVERLAP`` de
sobreposição; cada janela vira um vetor normalizado e os vetores são combinados por média
ponderada pela quantidade de tokens que cada janela acrescenta, seguida de normalização L2.
Resultado: um único vetor de 384 dimensões por texto, sem descartar o final.
"""
from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional, Sequence, Tuple

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSIONS = 384
VECTOR_SIMILARITY = "cosine"
VECTOR_INDEX = "trecho_embedding_vector"
VECTOR_LABEL = "Trecho"
VECTOR_PROPERTY = "embedding"

# Segmentação. Valores escolhidos pela avaliação em scripts/evaluate_embedding_strategies.py.
WINDOW_TOKENS = 126          # tokens de conteúdo por janela (+ 2 especiais = 128 posições)
WINDOW_OVERLAP = 32          # tokens repetidos entre janelas vizinhas
ARCHITECTURE_MAX_POSITIONS = 512  # usado só se o modelo não informar max_position_embeddings
AGGREGATION = "media-ponderada-tokens-novos-l2"
PIPELINE_REVISION = 2        # 1 = versão anterior: truncamento em 128 tokens, sem propriedade de versão


def pipeline_version(window_tokens: int = WINDOW_TOKENS, overlap: int = WINDOW_OVERLAP) -> str:
    """Identificador gravado em ``Trecho.embedding_pipeline_version``; muda junto com a estratégia."""
    return f"v{PIPELINE_REVISION}-janelas-{window_tokens}-sobreposicao-{overlap}-{AGGREGATION}"


EMBEDDING_PIPELINE_VERSION = pipeline_version()
INSTALL_HINT = "Instale as dependências da recuperação: pip install -r requirements.txt -r requirements-dev5.txt"

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


def token_windows(n_tokens: int, size: int, overlap: int) -> List[Tuple[int, int]]:
    """Janelas ``[início, fim)`` que cobrem todos os ``n_tokens``.

    Texto curto vira uma janela só. Nos longos, as janelas avançam ``size - overlap`` tokens e a
    última é alinhada ao fim do texto, para ter contexto completo e incluir o último token.
    """
    if size < 1:
        raise ValueError("size precisa ser >= 1")
    if not 0 <= overlap < size:
        raise ValueError("overlap precisa estar entre 0 e size - 1")
    if n_tokens <= size:
        return [(0, max(0, n_tokens))]
    stride = size - overlap
    spans, start = [], 0
    while start + size < n_tokens:
        spans.append((start, start + size))
        start += stride
    spans.append((n_tokens - size, n_tokens))
    return spans


def new_token_weights(spans: Sequence[Tuple[int, int]]) -> List[int]:
    """Tokens que cada janela acrescenta à cobertura (a sobreposição não conta duas vezes)."""
    weights, covered = [], 0
    for start, end in spans:
        weights.append(max(1, end - max(start, covered)))
        covered = max(covered, end)
    return weights


def uncovered_tokens(n_tokens: int, spans: Sequence[Tuple[int, int]]) -> int:
    """Quantos tokens de ``0..n_tokens`` não aparecem em nenhuma janela (esperado: 0)."""
    covered = set()
    for start, end in spans:
        covered.update(range(start, end))
    return sum(1 for index in range(n_tokens) if index not in covered)


def l2_normalize(vector: Sequence[float]) -> List[float]:
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("Vetor contém NaN ou infinito.")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("Vetor com norma nula ou inválida não pode ser normalizado.")
    return [value / norm for value in vector]


def aggregate_window_vectors(vectors: Sequence[Sequence[float]], weights: Sequence[float]) -> List[float]:
    """Média ponderada dos vetores das janelas (cada um normalizado antes), normalizada em L2."""
    if not vectors or len(vectors) != len(weights):
        raise ValueError("É preciso um peso para cada vetor de janela.")
    if not all(math.isfinite(w) and w > 0 for w in weights):
        raise ValueError("Pesos precisam ser positivos e finitos.")
    normalized = []
    for vector in vectors:
        validate_vector(vector)
        normalized.append(l2_normalize(vector))
    total = float(sum(weights))
    combined = [sum(w * v[i] for w, v in zip(weights, normalized)) / total for i in range(EMBEDDING_DIMENSIONS)]
    result = l2_normalize(combined)
    validate_vector(result)
    return result


def _special_tokens(tokenizer: Any) -> Tuple[List[int], List[int]]:
    """Descobre os tokens que o tokenizador põe antes e depois do conteúdo (ex.: <s> e </s>).

    ``build_inputs_with_special_tokens`` não serve: neste tokenizador ele não insere os especiais
    (transformers 4) ou nem existe (transformers 5).
    """
    full = tokenizer("a", add_special_tokens=True, verbose=False)["input_ids"]
    content = tokenizer("a", add_special_tokens=False, verbose=False)["input_ids"]
    for start in range(len(full) - len(content) + 1):
        if full[start:start + len(content)] == content:
            return list(full[:start]), list(full[start + len(content):])
    raise RuntimeError("Não foi possível identificar os tokens especiais do tokenizador.")


def _architecture_limit(model: Any) -> int:
    try:
        return int(model[0].auto_model.config.max_position_embeddings)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return ARCHITECTURE_MAX_POSITIONS


class SentenceEncoder:
    """Gera um vetor normalizado de 384 dimensões por texto, cobrindo o texto inteiro por janelas.

    Documentos (trechos) e perguntas passam pelo mesmo ``encode``: um texto que cabe em uma janela
    produz o mesmo vetor que ``SentenceTransformer.encode`` produziria.
    """

    def __init__(self, model_name: str = MODEL_NAME, model: Any = None,
                 window_tokens: int = WINDOW_TOKENS, overlap: int = WINDOW_OVERLAP):
        if model is None:
            try:
                # Import tardio: torch/sentence-transformers só são carregados quando necessários.
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(f"sentence-transformers não está instalado. {INSTALL_HINT}") from exc
            model = SentenceTransformer(model_name)
        dimension = model.get_sentence_embedding_dimension()
        if dimension != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"O modelo {model_name} produz {dimension} dimensões; o índice "
                f"{VECTOR_INDEX} espera {EMBEDDING_DIMENSIONS}."
            )
        token_windows(window_tokens + 1, window_tokens, overlap)  # valida os parâmetros
        self.model = model
        self.model_name = model_name
        self.tokenizer = model.tokenizer
        self.prefix, self.suffix = _special_tokens(self.tokenizer)
        self.special_tokens = len(self.prefix) + len(self.suffix)
        self.architecture_limit = _architecture_limit(model)
        if window_tokens + self.special_tokens > self.architecture_limit:
            raise ValueError(
                f"Janela de {window_tokens} tokens + {self.special_tokens} especiais excede as "
                f"{self.architecture_limit} posições da arquitetura."
            )
        self.default_max_seq_length: Optional[int] = getattr(model, "max_seq_length", None)
        self.window_tokens = window_tokens
        self.overlap = overlap
        self.max_seq_length = window_tokens + self.special_tokens  # limite efetivo por janela
        self.pipeline_version = pipeline_version(window_tokens, overlap)
        if hasattr(model, "max_seq_length"):
            model.max_seq_length = self.max_seq_length

    def content_token_ids(self, text: str) -> List[int]:
        """Tokens de conteúdo do texto inteiro, sem os especiais e sem corte."""
        return list(self.tokenizer(text or "", add_special_tokens=False, verbose=False)["input_ids"])

    def count_tokens(self, texts: Sequence[str]) -> List[int]:
        """Tokens de cada texto incluindo os especiais, como o modelo os veria sem segmentação."""
        return [len(self.content_token_ids(text)) + self.special_tokens for text in texts]

    def window_plan(self, text: str) -> Dict[str, Any]:
        """Janelas usadas para um texto: tokens totais, intervalos, pesos e tokens não cobertos."""
        n_tokens = len(self.content_token_ids(text))
        spans = token_windows(n_tokens, self.window_tokens, self.overlap)
        return {
            "tokens": n_tokens,
            "janelas": spans,
            "pesos": new_token_weights(spans),
            "tokens_nao_representados": uncovered_tokens(n_tokens, spans),
        }

    def _forward_ids(self, windows: Sequence[Sequence[int]]) -> List[List[float]]:
        """Executa o modelo sobre janelas já tokenizadas (prefixo + conteúdo + sufixo)."""
        import torch

        sequences = [self.prefix + list(ids) + self.suffix for ids in windows]
        width = max(len(seq) for seq in sequences)
        pad = self.tokenizer.pad_token_id if self.tokenizer.pad_token_id is not None else 0
        device = getattr(self.model, "device", "cpu")
        features = {
            "input_ids": torch.tensor([seq + [pad] * (width - len(seq)) for seq in sequences], device=device),
            "attention_mask": torch.tensor([[1] * len(seq) + [0] * (width - len(seq)) for seq in sequences],
                                           device=device),
        }
        if "token_type_ids" in getattr(self.tokenizer, "model_input_names", []):
            features["token_type_ids"] = torch.zeros_like(features["input_ids"])
        with torch.no_grad():
            output = self.model(features)["sentence_embedding"]
        return [list(map(float, row)) for row in output.float().cpu().tolist()]

    def _window_weights(self, spans: Sequence[Tuple[int, int]]) -> List[int]:
        return new_token_weights(spans)

    def encode(self, texts: Sequence[str], batch_size: int = 32) -> List[List[float]]:
        plans = []
        windows: List[List[int]] = []
        for text in texts:
            ids = self.content_token_ids(text)
            spans = token_windows(len(ids), self.window_tokens, self.overlap)
            plans.append((len(windows), len(spans), self._window_weights(spans)))
            windows.extend(ids[start:end] for start, end in spans)

        window_vectors: List[List[float]] = []
        for start in range(0, len(windows), batch_size):
            window_vectors.extend(self._forward_ids(windows[start:start + batch_size]))

        return [
            aggregate_window_vectors(window_vectors[first:first + count], weights)
            for first, count, weights in plans
        ]


def truncation_summary(token_counts: Sequence[int], limit: int) -> dict:
    """Quantos textos passam do limite do modelo; acima dele o embedding ignora o restante."""
    counts = sorted(token_counts)
    return {
        "total": len(counts),
        "limite": limit,
        "acima_do_limite": sum(1 for count in counts if count > limit),
        "minimo": counts[0] if counts else None,
        "mediana": statistics.median(counts) if counts else None,
        "maximo": counts[-1] if counts else None,
    }


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
