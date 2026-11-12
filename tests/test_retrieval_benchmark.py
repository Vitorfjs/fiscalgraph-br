import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "data" / "fixtures" / "retrieval_benchmark.json"
TRECHOS_PATH = ROOT / "data" / "processed" / "trechos.jsonl"


class RetrievalMetricsTests(unittest.TestCase):
    def test_precision_recall_mrr_and_ndcg_exact_values(self):
        from app.services.benchmark import (
            ndcg_at_k,
            precision_at_k,
            recall_at_k,
            reciprocal_rank,
        )

        retrieved = ["T2", "T1", "T9", "T3", "T8"]
        relevant = {"T1", "T3", "T4"}

        # Em top-5: hits em posicoes 2 (T1) e 4 (T3) -> 2/5 e 2/3
        self.assertAlmostEqual(precision_at_k(retrieved, relevant, k=5), 2 / 5)
        self.assertAlmostEqual(recall_at_k(retrieved, relevant, k=5), 2 / 3)
        self.assertAlmostEqual(reciprocal_rank(retrieved, relevant, k=5), 1 / 2)

        dcg = (1.0 / math.log2(2 + 1)) + (1.0 / math.log2(4 + 1))
        idcg = (1.0 / math.log2(1 + 1)) + (1.0 / math.log2(2 + 1)) + (1.0 / math.log2(3 + 1))
        self.assertAlmostEqual(ndcg_at_k(retrieved, relevant, k=5), dcg / idcg)

        # Sem relevantes dentro de top-k=1
        self.assertEqual(precision_at_k(retrieved, relevant, k=1), 0.0)
        self.assertEqual(recall_at_k(retrieved, relevant, k=1), 0.0)
        self.assertEqual(reciprocal_rank(retrieved, relevant, k=1), 0.0)
        self.assertEqual(ndcg_at_k(retrieved, relevant, k=1), 0.0)

        # Ranking ideal retorna 1.0 em nDCG@K
        self.assertAlmostEqual(ndcg_at_k(["T1", "T3", "T4"], relevant, k=5), 1.0)

    def test_edge_cases_and_invalid_k(self):
        from app.services.benchmark import precision_at_k, recall_at_k

        self.assertEqual(precision_at_k([], {"T1"}, k=5), 0.0)
        self.assertEqual(recall_at_k(["T1"], set(), k=5), 0.0)
        with self.assertRaises(ValueError):
            precision_at_k(["T1"], {"T1"}, k=0)

    def test_evaluate_retrieval_rankings_ignores_abstention_cases_and_groups_categories(self):
        from app.services.benchmark import evaluate_retrieval_rankings

        cases = [
            {
                "id": "Q1",
                "category": "cnpj_exato",
                "question": "CNPJ 1",
                "expected_trecho_ids": ["T1"],
                "expected_abstained": False,
            },
            {
                "id": "Q2",
                "category": "norma_legal",
                "question": "Lei X",
                "expected_trecho_ids": ["T2", "T3"],
                "expected_abstained": False,
            },
            {
                "id": "Q3",
                "category": "fora_de_dominio",
                "question": "Bolo",
                "expected_trecho_ids": [],
                "expected_abstained": True,
            },
        ]
        retrieved_by_case = {
            "Q1": ["T1", "T9"],
            "Q2": ["T9", "T2"],
            "Q3": ["T1"],
        }

        summary = evaluate_retrieval_rankings(cases, retrieved_by_case, k=2)
        self.assertEqual(summary["evaluated_queries"], 2)
        self.assertAlmostEqual(summary["precision_at_k"], (0.5 + 0.5) / 2)
        self.assertAlmostEqual(summary["recall_at_k"], (1.0 + 0.5) / 2)
        self.assertAlmostEqual(summary["mrr_at_k"], (1.0 + 0.5) / 2)
        self.assertAlmostEqual(summary["hit_rate_at_k"], 1.0)
        self.assertIn("cnpj_exato", summary["by_category"])
        self.assertIn("norma_legal", summary["by_category"])
        self.assertNotIn("fora_de_dominio", summary["by_category"])

    def test_evaluate_abstention_decisions_computes_confusion_and_accuracy(self):
        from app.services.benchmark import evaluate_abstention_decisions

        cases = [
            {"id": "Q1", "category": "cnpj_exato", "question": "p1", "expected_abstained": False},
            {"id": "Q2", "category": "cnpj_ausente", "question": "p2", "expected_abstained": True},
            {"id": "Q3", "category": "fora_de_dominio", "question": "p3", "expected_abstained": True},
        ]
        decisions = {"Q1": False, "Q2": True, "Q3": False}

        report = evaluate_abstention_decisions(cases, decisions)
        self.assertEqual(report["total_cases"], 3)
        self.assertEqual(report["correct"], 2)
        self.assertAlmostEqual(report["accuracy"], 2 / 3)
        self.assertEqual(report["mismatches"][0]["id"], "Q3")

    def test_summarize_multihop_comparison_aggregates_real_and_synthetic(self):
        from app.services.benchmark import summarize_multihop_comparison

        real_runs = [
            {
                "pair": ["00356328", "01340937"],
                "paths": [{"kind": "atividade_cnae", "length": 4}],
            },
            {
                "pair": ["00002776", "00356328"],
                "paths": [],
            },
        ]
        synthetic_run = {"paths": [{"kind": "societario", "length": 2}]}

        summary = summarize_multihop_comparison(real_runs, synthetic_run)
        self.assertEqual(summary["real"]["pairs_tested"], 2)
        self.assertEqual(summary["real"]["pairs_with_path"], 1)
        self.assertEqual(summary["real"]["societario_paths"], 0)
        self.assertEqual(summary["real"]["cnae_paths"], 1)
        self.assertEqual(summary["synthetic"]["societario_paths"], 1)
        self.assertEqual(summary["synthetic"]["shortest_length"], 2)

    def test_format_benchmark_markdown_renders_comparison_and_multihop(self):
        from app.services.benchmark import format_benchmark_markdown

        report = {
            "k": 5,
            "dataset_version": "1.0",
            "total_cases": 20,
            "modes": {
                "vector": {
                    "evaluated_queries": 16,
                    "precision_at_k": 0.25,
                    "recall_at_k": 0.60,
                    "mrr_at_k": 0.65,
                    "ndcg_at_k": 0.62,
                    "hit_rate_at_k": 0.80,
                    "by_category": {},
                    "cases": [],
                },
                "fulltext": {
                    "evaluated_queries": 16,
                    "precision_at_k": 0.30,
                    "recall_at_k": 0.70,
                    "mrr_at_k": 0.75,
                    "ndcg_at_k": 0.72,
                    "hit_rate_at_k": 0.85,
                    "by_category": {},
                    "cases": [],
                },
                "hybrid": {
                    "evaluated_queries": 16,
                    "precision_at_k": 0.35,
                    "recall_at_k": 0.85,
                    "mrr_at_k": 0.90,
                    "ndcg_at_k": 0.88,
                    "hit_rate_at_k": 0.95,
                    "by_category": {},
                    "cases": [],
                },
            },
            "abstention": {
                "total_cases": 20,
                "correct": 20,
                "accuracy": 1.0,
                "true_abstentions": 4,
                "true_answers": 16,
                "false_abstentions": 0,
                "missed_abstentions": 0,
                "mismatches": [],
            },
            "multihop": {
                "real": {
                    "pairs_tested": 4,
                    "pairs_with_path": 3,
                    "societario_paths": 0,
                    "cnae_paths": 3,
                    "mencao_paths": 0,
                    "other_paths": 0,
                    "lengths": [4, 4, 4],
                },
                "synthetic": {
                    "paths_found": 1,
                    "societario_paths": 1,
                    "shortest_length": 2,
                },
            },
            "multihop_details": {"real_runs": [], "synthetic_run": {}},
        }

        md = format_benchmark_markdown(report)
        self.assertIn("Precision@5", md)
        self.assertIn("Recall@5", md)
        self.assertIn("MRR@5", md)
        self.assertIn("nDCG@5", md)
        self.assertIn("Híbrido (RRF)", md)
        self.assertIn("Multi-hop", md)
        self.assertIn("100.0%", md)


class BenchmarkDatasetIntegrityTests(unittest.TestCase):
    def test_benchmark_dataset_covers_categories_and_matches_real_trechos(self):
        self.assertTrue(BENCHMARK_PATH.exists(), f"Dataset ausente em {BENCHMARK_PATH}")
        dataset = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
        cases = dataset.get("cases", [])

        self.assertGreaterEqual(len(cases), 15)
        self.assertLessEqual(len(cases), 25)
        categories = {case["category"] for case in cases}
        self.assertGreaterEqual(len(categories), 10)

        trechos_by_id = {}
        with TRECHOS_PATH.open(encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                trechos_by_id[item["trecho_id"]] = item

        for case in cases:
            self.assertIn("id", case)
            self.assertIn("category", case)
            self.assertIn("question", case)
            self.assertIsInstance(case["expected_abstained"], bool)
            if case["expected_abstained"]:
                self.assertEqual(case["expected_trecho_ids"], [])
            else:
                self.assertTrue(case["expected_trecho_ids"], f"{case['id']} sem trechos esperados")
                for trecho_id in case["expected_trecho_ids"]:
                    self.assertIn(trecho_id, trechos_by_id, f"{trecho_id} ausente em trechos.jsonl")
                if case.get("expected_registro_ids"):
                    actual_regs = {trechos_by_id[tid]["registro_id"] for tid in case["expected_trecho_ids"]}
                    self.assertEqual(set(case["expected_registro_ids"]), actual_regs)


if __name__ == "__main__":
    unittest.main()
