#!/usr/bin/env python3
"""Compara estratégias de embedding dos Trecho na recuperação vetorial (dev5).

Não há perguntas rotuladas no projeto, então a avaliação é autossupervisionada e explícita:

- consultas "final": as últimas palavras de cada trecho que passa de 126 tokens de conteúdo,
  tiradas só da parte que o truncamento em 128 posições ignorava;
- consultas "inicio": as primeiras palavras de cada um dos 54 trechos (checa regressão);
- relevante = todo trecho cujo texto contém a consulta literalmente (há textos legais repetidos).

Métricas sobre busca vetorial pura (cosseno exato entre os 54 vetores, sem Neo4j): acerto@1,
acerto@5 e MRR do primeiro relevante. Também lista o top-3 das perguntas manuais documentadas.
A avaliação mede se o conteúdo está representado no vetor, não a qualidade semântica em paráfrases.

Uso:
    python scripts/evaluate_embedding_strategies.py             # compara estratégias, sem Neo4j
    python scripts/evaluate_embedding_strategies.py --hibrido   # sistema real no Neo4j (requer .env)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRECHOS = ROOT / "data" / "processed" / "trechos.jsonl"
QUERY_WORDS = 30
TRUNCATED_CONTENT_TOKENS = 126  # 128 posições - 2 especiais (estratégia anterior)
MANUAL_QUESTIONS = (
    "Quais empresas foram declaradas inidôneas para licitar com a administração pública?",
    "empresa impedida de fechar contratos com o governo",
    "Lei 12.846 publicação extraordinária da decisão condenatória",
    "trecho que cita o CNPJ 01.340.937/0001-79",
    "receita de bolo de chocolate",
)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def relevant_set(query: str, texts: Sequence[str]) -> Set[int]:
    needle = normalize(query)
    return {i for i, text in enumerate(texts) if needle in normalize(text)}


def rank_of_first_relevant(scores: Sequence[float], relevant: Set[int]) -> int:
    """Posição 1-based do melhor relevante; empates contam a favor (textos idênticos empatam)."""
    best = max(scores[i] for i in relevant)
    return 1 + sum(1 for score in scores if score > best + 1e-9)


def metrics(ranks: Sequence[Optional[int]]) -> Dict[str, float]:
    """``None`` = nenhum relevante entre os resultados devolvidos (conta 0 no MRR)."""
    n = len(ranks)
    return {
        "consultas": n,
        "acerto@1": sum(r is not None and r <= 1 for r in ranks) / n,
        "acerto@5": sum(r is not None and r <= 5 for r in ranks) / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
    }


def evaluate_hybrid(queries: Dict[str, List[str]]) -> int:
    """Avalia o sistema real (retrieve_context: vetorial + full-text + RRF) com os vetores do Neo4j."""
    from app.services.retrieval import GraphHybridRetriever

    retriever = GraphHybridRetriever.from_env()
    try:
        with retriever.driver.session(database=retriever.database) as session:
            stored = session.run(
                "MATCH (t:Trecho) RETURN count(t.embedding) AS com_embedding, "
                "collect(DISTINCT coalesce(t.embedding_pipeline_version, 'v1-truncado-128 (sem propriedade)')) AS versoes"
            ).single()
        print(f"Embeddings no Neo4j: {stored['com_embedding']} | versões: {stored['versoes']}")
        print("Sistema híbrido (retrieve_context, top_k=20); MRR@20, ausente do top 20 conta 0\n")
        print("Consultas | n  | @1    @5    MRR  | 1º resultado veio de: ambas / só vetorial / só full-text")
        for name, qs in queries.items():
            ranks, origin = [], {"ambas": 0, "vetorial": 0, "full-text": 0}
            for query in qs:
                chunks = retriever.retrieve_context(query, top_k=20)["chunks"]
                needle = normalize(query)
                ranks.append(next((i for i, c in enumerate(chunks, 1) if needle in normalize(c["texto"])), None))
                top = chunks[0]
                key = "ambas" if top["vector_rank"] and top["fulltext_rank"] else (
                    "vetorial" if top["vector_rank"] else "full-text")
                origin[key] += 1
            m = metrics(ranks)
            print(f"{name:9s} | {m['consultas']:2d} | {m['acerto@1']:.2f}  {m['acerto@5']:.2f}  {m['mrr']:.2f} | "
                  f"{origin['ambas']} / {origin['vetorial']} / {origin['full-text']}")
    finally:
        retriever.close()
    return 0


def tail_query(text: str, tokenizer, cut_tokens: int) -> str:
    """Últimas palavras do trecho, todas posteriores ao ponto de corte do truncamento anterior."""
    offsets = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
    cut_char = offsets[cut_tokens][0]
    words = text[cut_char:].split()
    if cut_char > 0 and not text[cut_char - 1].isspace() and words:
        words = words[1:]  # o corte caiu no meio de uma palavra: descarta o fragmento
    return " ".join(words[-QUERY_WORDS:])


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compara estratégias de embedding dos Trecho.")
    parser.add_argument("--hibrido", action="store_true",
                        help="Avalia o sistema real no Neo4j (vetores gravados + full-text + RRF) em vez de comparar estratégias")
    args = parser.parse_args(argv)

    import numpy as np

    from app.services.embeddings import SentenceEncoder

    items = [json.loads(line) for line in TRECHOS.open(encoding="utf-8") if line.strip()]
    texts = [item["texto"] for item in items]
    base = SentenceEncoder()
    tokenizer, model = base.tokenizer, base.model
    n_tokens = [len(base.content_token_ids(t)) for t in texts]
    long_idx = [i for i, n in enumerate(n_tokens) if n > TRUNCATED_CONTENT_TOKENS]

    queries = {
        "final": [tail_query(texts[i], tokenizer, TRUNCATED_CONTENT_TOKENS) for i in long_idx],
        "inicio": [" ".join(t.split()[:QUERY_WORDS]) for t in texts],
    }
    relevants = {name: [relevant_set(q, texts) for q in qs] for name, qs in queries.items()}
    assert all(rel for rels in relevants.values() for rel in rels), "consulta sem trecho relevante"
    if args.hibrido:
        return evaluate_hybrid(queries)

    def single_pass(limit: int):
        def run(batch: Sequence[str]) -> List[List[float]]:
            model.max_seq_length = limit
            return model.encode(list(batch), normalize_embeddings=True, show_progress_bar=False).tolist()
        return run

    class UniformWeightEncoder(SentenceEncoder):
        """Variante de comparação: média simples, cada janela com o mesmo peso."""

        def _window_weights(self, spans):
            return [1] * len(spans)

    windowed = {}
    for window, overlap in ((126, 32), (254, 64), (510, 64)):
        windowed[(window, overlap)] = SentenceEncoder(model=model, window_tokens=window, overlap=overlap)
    uniform = UniformWeightEncoder(model=model, window_tokens=126, overlap=32)

    strategies = {
        "truncado-128 (anterior)": (single_pass(128), None),
        "passada-unica-512": (single_pass(512), None),
        "janelas-128 (126+32)": (windowed[(126, 32)].encode, windowed[(126, 32)]),
        "janelas-128 media simples": (uniform.encode, uniform),
        "janelas-256 (254+64)": (windowed[(254, 64)].encode, windowed[(254, 64)]),
        "janelas-512 (510+64)": (windowed[(510, 64)].encode, windowed[(510, 64)]),
    }

    print(f"Trechos: {len(texts)} | com mais de {TRUNCATED_CONTENT_TOKENS} tokens de conteúdo: {len(long_idx)} | "
          f"maior: {max(n_tokens)} tokens de conteúdo")
    for name, qs in queries.items():
        sizes = [len(r) for r in relevants[name]]
        print(f"Consultas '{name}': {len(qs)} | trechos relevantes por consulta: mín. {min(sizes)}, "
              f"média {sum(sizes) / len(sizes):.1f}, máx. {max(sizes)}")

    print("\nEstratégia                 | janelas | não repr. | final: @1    @5    MRR  | início: @1    @5    MRR  | tempo")
    tops = {}
    for name, (encode, encoder) in strategies.items():
        start = time.time()
        doc = np.array(encode(texts))
        elapsed = time.time() - start
        windows = sum(len(encoder.window_plan(t)["janelas"]) for t in texts) if encoder else len(texts)
        limit = (encoder.window_tokens if encoder else (126 if "128" in name else 510))
        missing = 0 if encoder else sum(max(0, n - limit) for n in n_tokens)
        row = {}
        for qname, qs in queries.items():
            qv = np.array(encode(qs))
            ranks = [rank_of_first_relevant(doc @ q, rel) for q, rel in zip(qv, relevants[qname])]
            row[qname] = metrics(ranks)
        f, h = row["final"], row["inicio"]
        print(f"{name:26s} | {windows:7d} | {missing:9d} | {f['acerto@1']:.2f}  {f['acerto@5']:.2f}  {f['mrr']:.2f} | "
              f"{h['acerto@1']:.2f}  {h['acerto@5']:.2f}  {h['mrr']:.2f} | {elapsed:.1f}s")
        mq = np.array(encode(MANUAL_QUESTIONS))
        tops[name] = [[items[i]["registro_id"] for i in np.argsort(-(doc @ q), kind="stable")[:3]] for q in mq]

    print("\nTop-3 vetorial das perguntas manuais (registro_id):")
    for qi, question in enumerate(MANUAL_QUESTIONS):
        print(f"- {question}")
        for name in strategies:
            print(f"    {name:26s} {', '.join(tops[name][qi])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
