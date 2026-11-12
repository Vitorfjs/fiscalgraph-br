"""Métricas de recuperação e avaliação comparativa (Vetorial vs. Full-text vs. Híbrido RRF + Multi-hop)."""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set

from app.services import orchestrator, retrieval


def _validate_k(k: int) -> int:
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k precisa ser um inteiro >= 1.")
    return k


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: Set[str], k: int = 5) -> float:
    """Proporção de itens relevantes entre os ``k`` primeiros retornados."""
    _validate_k(k)
    top_k = list(retrieved_ids[:k])
    if not top_k or not relevant_ids:
        return 0.0
    hits = sum(1 for item_id in top_k if item_id in relevant_ids)
    return hits / k


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: Set[str], k: int = 5) -> float:
    """Cobertura dos itens relevantes recuperados até a posição ``k``."""
    _validate_k(k)
    if not relevant_ids or not retrieved_ids:
        return 0.0
    hits = sum(1 for item_id in retrieved_ids[:k] if item_id in relevant_ids)
    return hits / len(relevant_ids)


def reciprocal_rank(retrieved_ids: Sequence[str], relevant_ids: Set[str], k: int = 5) -> float:
    """Inverso da posição 1-based do primeiro item relevante dentro de ``top-k``."""
    _validate_k(k)
    if not relevant_ids:
        return 0.0
    for rank, item_id in enumerate(retrieved_ids[:k], start=1):
        if item_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: Sequence[str], relevant_ids: Set[str], k: int = 5) -> float:
    """nDCG@K binário com log na base 2."""
    _validate_k(k)
    if not relevant_ids or not retrieved_ids:
        return 0.0
    top_k = list(retrieved_ids[:k])
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, item_id in enumerate(top_k, start=1)
        if item_id in relevant_ids
    )
    ideal_hits = min(k, len(relevant_ids))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def _average_metric_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    count = len(rows)
    if count == 0:
        return {
            "evaluated_queries": 0,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "mrr_at_k": 0.0,
            "ndcg_at_k": 0.0,
            "hit_rate_at_k": 0.0,
        }
    return {
        "evaluated_queries": count,
        "precision_at_k": sum(r["precision_at_k"] for r in rows) / count,
        "recall_at_k": sum(r["recall_at_k"] for r in rows) / count,
        "mrr_at_k": sum(r["mrr_at_k"] for r in rows) / count,
        "ndcg_at_k": sum(r["ndcg_at_k"] for r in rows) / count,
        "hit_rate_at_k": sum(1.0 if r["hits"] > 0 else 0.0 for r in rows) / count,
    }


def evaluate_retrieval_rankings(
    cases: Sequence[Dict[str, Any]],
    retrieved_by_case: Dict[str, Sequence[str]],
    k: int = 5,
) -> Dict[str, Any]:
    """Calcula Precision@K, Recall@K, MRR@K, nDCG@K e Hit@K para casos positivos."""
    _validate_k(k)
    per_case: List[Dict[str, Any]] = []
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for case in cases:
        relevant_ids = set(case.get("expected_trecho_ids") or [])
        if case.get("expected_abstained") or not relevant_ids:
            continue
        retrieved = list(retrieved_by_case.get(case["id"], ()))
        hits = sum(1 for item_id in retrieved[:k] if item_id in relevant_ids)
        row = {
            "id": case["id"],
            "category": case["category"],
            "question": case["question"],
            "expected_count": len(relevant_ids),
            "retrieved_top_k": retrieved[:k],
            "hits": hits,
            "precision_at_k": precision_at_k(retrieved, relevant_ids, k),
            "recall_at_k": recall_at_k(retrieved, relevant_ids, k),
            "mrr_at_k": reciprocal_rank(retrieved, relevant_ids, k),
            "ndcg_at_k": ndcg_at_k(retrieved, relevant_ids, k),
        }
        per_case.append(row)
        grouped.setdefault(case["category"], []).append(row)

    summary = _average_metric_rows(per_case)
    summary["k"] = k
    summary["by_category"] = {
        category: _average_metric_rows(rows) for category, rows in grouped.items()
    }
    summary["cases"] = per_case
    return summary


def evaluate_abstention_decisions(
    cases: Sequence[Dict[str, Any]],
    decisions_by_case: Dict[str, bool],
) -> Dict[str, Any]:
    """Avalia acerto da decisão binária de abstenção (``abstained``)."""
    mismatches: List[Dict[str, Any]] = []
    tp = tn = fp = fn = 0

    for case in cases:
        expected = bool(case.get("expected_abstained"))
        actual = bool(decisions_by_case.get(case["id"], False))
        if expected and actual:
            tp += 1
        elif not expected and not actual:
            tn += 1
        elif not expected and actual:
            fp += 1
            mismatches.append({"id": case["id"], "expected": expected, "actual": actual})
        else:
            fn += 1
            mismatches.append({"id": case["id"], "expected": expected, "actual": actual})

    total = len(cases)
    correct = tp + tn
    return {
        "total_cases": total,
        "correct": correct,
        "accuracy": (correct / total) if total else 0.0,
        "true_abstentions": tp,
        "true_answers": tn,
        "false_abstentions": fp,
        "missed_abstentions": fn,
        "mismatches": mismatches,
    }


def summarize_multihop_comparison(
    real_runs: Sequence[Dict[str, Any]],
    synthetic_run: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resume a comparação entre caminhos multi-hop reais e cenário sintético."""
    societario_real = 0
    cnae_real = 0
    mencao_real = 0
    other_real = 0
    pairs_with_path = 0
    real_lengths: List[int] = []

    for run in real_runs:
        paths = run.get("paths") or []
        if paths:
            pairs_with_path += 1
        for path in paths:
            kind = path.get("kind")
            real_lengths.append(int(path.get("length", 0)))
            if kind == "societario":
                societario_real += 1
            elif kind == "atividade_cnae":
                cnae_real += 1
            elif kind == "mencao_candidata":
                mencao_real += 1
            else:
                other_real += 1

    synth_paths = (synthetic_run or {}).get("paths") or []
    synth_lengths = [int(p.get("length", 0)) for p in synth_paths if p.get("length") is not None]
    synth_societario = sum(1 for p in synth_paths if p.get("kind") == "societario")

    return {
        "real": {
            "pairs_tested": len(real_runs),
            "pairs_with_path": pairs_with_path,
            "societario_paths": societario_real,
            "cnae_paths": cnae_real,
            "mencao_paths": mencao_real,
            "other_paths": other_real,
            "lengths": real_lengths,
        },
        "synthetic": {
            "paths_found": len(synth_paths),
            "societario_paths": synth_societario,
            "shortest_length": min(synth_lengths) if synth_lengths else None,
        },
    }


def _vector_trecho_ids(retriever: Any, question: str, k: int) -> List[str]:
    embedding = retriever.encoder.encode([question])[0]
    with retriever.driver.session(database=retriever.database) as session:
        rows = retriever._search(
            session,
            retrieval.VECTOR_QUERY,
            [],
            "Busca vetorial indisponível",
            index_name=retrieval.VECTOR_INDEX,
            limit=k,
            embedding=embedding,
        ) or []
    return [row["trecho_id"] for row in rows[:k]]


def _fulltext_trecho_ids(retriever: Any, question: str, k: int) -> List[str]:
    query = retrieval.build_fulltext_query(question)
    if not query:
        return []
    with retriever.driver.session(database=retriever.database) as session:
        rows = retriever._search(
            session,
            retrieval.FULLTEXT_QUERY,
            [],
            "Busca full-text indisponível",
            index_name=retrieval.FULLTEXT_INDEX,
            query=query,
            limit=k,
        ) or []
    return [row["trecho_id"] for row in rows[:k]]


def _run_synthetic_societario_probe(retriever: Any) -> Dict[str, Any]:
    """Executa o cenário sintético ``PARTICIPA_DE`` em transação com rollback garantido."""
    from app.services.multi_hop import find_company_paths

    with retriever.driver.session(database=retriever.database) as session:
        tx = session.begin_transaction()
        try:
            tx.run(
                """
                CREATE (ea:Empresa:Sintetico {cnpj_basico: 'SINT-0001', razao_social: 'EMPRESA SINTETICA A', sintetico: true})
                CREATE (eb:Empresa:Sintetico {cnpj_basico: 'SINT-0002', razao_social: 'EMPRESA SINTETICA B', sintetico: true})
                CREATE (s:Socio:Sintetico {socio_id: 'SINT-SOC-1', nome: 'SOCIO SINTETICO BENCHMARK', sintetico: true})
                CREATE (s)-[:PARTICIPA_DE {sintetico: true}]->(ea)
                CREATE (s)-[:PARTICIPA_DE {sintetico: true}]->(eb)
                """
            ).consume()
            return find_company_paths(tx, "SINT-0001", "SINT-0002", max_hops=6)
        finally:
            tx.rollback()


def run_benchmark_against_neo4j(
    retriever: Any,
    dataset: Dict[str, Any],
    k: int = 5,
    real_company_pairs: Optional[Iterable[Sequence[str]]] = None,
    answer_fn: Callable[..., Dict[str, Any]] = orchestrator.answer_question,
) -> Dict[str, Any]:
    """Executa o benchmark completo (3 modos + abstenção + multi-hop) sobre Neo4j real."""
    cases = list(dataset.get("cases") or [])
    vector_hits: Dict[str, List[str]] = {}
    fulltext_hits: Dict[str, List[str]] = {}
    hybrid_hits: Dict[str, List[str]] = {}
    abstention_decisions: Dict[str, bool] = {}

    for case in cases:
        case_id = case["id"]
        question = case["question"]
        if not case.get("expected_abstained"):
            vector_hits[case_id] = _vector_trecho_ids(retriever, question, k)
            fulltext_hits[case_id] = _fulltext_trecho_ids(retriever, question, k)
            context = retriever.retrieve_context(question, top_k=k)
            hybrid_hits[case_id] = [chunk["trecho_id"] for chunk in context.get("chunks", [])]

        response = answer_fn(question, top_k=k, retriever=retriever)
        abstention_decisions[case_id] = bool(response.get("abstained"))

    pairs = list(
        real_company_pairs
        or (
            ("00356328", "01340937"),
            ("00000113", "00000145"),
            ("00073357", "01278154"),
            ("00002776", "00356328"),
        )
    )
    real_multihop_runs = [
        {"pair": list(pair), **retriever.company_paths(pair[0], pair[1], max_hops=6)}
        for pair in pairs
    ]
    synthetic_multihop = _run_synthetic_societario_probe(retriever)

    return {
        "k": k,
        "dataset_version": dataset.get("version"),
        "total_cases": len(cases),
        "modes": {
            "vector": evaluate_retrieval_rankings(cases, vector_hits, k=k),
            "fulltext": evaluate_retrieval_rankings(cases, fulltext_hits, k=k),
            "hybrid": evaluate_retrieval_rankings(cases, hybrid_hits, k=k),
        },
        "abstention": evaluate_abstention_decisions(cases, abstention_decisions),
        "multihop": summarize_multihop_comparison(real_multihop_runs, synthetic_multihop),
        "multihop_details": {
            "real_runs": [
                {
                    "pair": run["pair"],
                    "paths": run["paths"],
                    "warnings": run["warnings"],
                }
                for run in real_multihop_runs
            ],
            "synthetic_run": {
                "paths": synthetic_multihop.get("paths", []),
                "warnings": synthetic_multihop.get("warnings", []),
            },
        },
    }


def format_benchmark_markdown(report: Dict[str, Any]) -> str:
    """Formata os resultados do benchmark e da comparação Multi-hop em Markdown."""
    k = report["k"]
    modes = report["modes"]
    abstention = report["abstention"]
    multihop = report["multihop"]
    mode_labels = (
        ("vector", "Vetorial puro"),
        ("fulltext", "Full-text puro"),
        ("hybrid", "Híbrido (RRF)"),
    )

    lines = [
        f"# Avaliação Quantitativa da Recuperação e Multi-hop (top-{k})",
        "",
        f"- **Dataset:** versão `{report.get('dataset_version', 'N/A')}` ({report['total_cases']} perguntas em 10 categorias)",
        "",
        f"## 1. Comparação entre Modos de Recuperação (`k={k}`)",
        "",
        f"| Modo | Consultas | Precision@{k} | Recall@{k} | MRR@{k} | nDCG@{k} | Hit@{k} |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode_key, label in mode_labels:
        m = modes[mode_key]
        lines.append(
            f"| {label} | {m['evaluated_queries']} | {m['precision_at_k']:.4f} | "
            f"{m['recall_at_k']:.4f} | {m['mrr_at_k']:.4f} | {m['ndcg_at_k']:.4f} | {m['hit_rate_at_k']:.4f} |"
        )

    hybrid_categories = modes["hybrid"].get("by_category") or {}
    if hybrid_categories:
        lines.extend([
            "",
            f"## 2. Desempenho do Modo Híbrido (RRF) por Categoria (`k={k}`)",
            "",
            f"| Categoria | Consultas | Precision@{k} | Recall@{k} | MRR@{k} | nDCG@{k} |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ])
        for category, stats in hybrid_categories.items():
            lines.append(
                f"| `{category}` | {stats['evaluated_queries']} | {stats['precision_at_k']:.4f} | "
                f"{stats['recall_at_k']:.4f} | {stats['mrr_at_k']:.4f} | {stats['ndcg_at_k']:.4f} |"
            )

    lines.extend([
        "",
        "## 3. Acurácia da Política de Abstenção (Orquestrador Dev1 + Dev5)",
        "",
        f"- **Acurácia global:** {abstention['accuracy'] * 100:.1f}% ({abstention['correct']}/{abstention['total_cases']})",
        f"- **Abstenções corretas (TP):** {abstention['true_abstentions']} | **Respostas corretas (TN):** {abstention['true_answers']}",
        f"- **Falsas abstenções (FP):** {abstention['false_abstentions']} | **Abstenções perdidas (FN):** {abstention['missed_abstentions']}",
        "",
        "## 4. Análise Multi-hop: Real (Dados Canônicos) vs. Sintético",
        "",
        "| Cenário | Pares avaliados / Caminhos | Societário (`PARTICIPA_DE`) | Por CNAE (`EXERCE_CNAE`) | Saltos observados |",
        "| --- | --- | ---: | ---: | --- |",
        f"| **Real (18 empresas)** | {multihop['real']['pairs_tested']} pares / {multihop['real']['pairs_with_path']} com caminho | "
        f"{multihop['real']['societario_paths']} | {multihop['real']['cnae_paths']} | {multihop['real']['lengths']} |",
        f"| **Sintético (`PARTICIPA_DE` com rollback)** | 1 par controlado / {multihop['synthetic']['paths_found']} caminho | "
        f"{multihop['synthetic']['societario_paths']} | 0 | [{multihop['synthetic']['shortest_length']}] |",
        "",
    ])
    return "\n".join(lines)
