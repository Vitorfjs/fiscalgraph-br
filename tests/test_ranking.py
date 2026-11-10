"""Testes do Reciprocal Rank Fusion (dev5). Não exigem Neo4j nem modelo de embeddings.

Executar na raiz do repositório:
    python -m unittest discover -s tests -p "test_ranking.py" -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ranking import DEFAULT_RRF_K, reciprocal_rank_fusion  # noqa: E402


def by_id(result):
    return {item["trecho_id"]: item for item in result}


class RRFFormulaTests(unittest.TestCase):
    def test_default_k_is_60(self):
        self.assertEqual(DEFAULT_RRF_K, 60)

    def test_score_is_sum_of_reciprocal_ranks(self):
        result = by_id(reciprocal_rank_fusion(["A", "B"], ["B"]))
        self.assertAlmostEqual(result["A"]["rrf_score"], 1 / 61)
        self.assertAlmostEqual(result["B"]["rrf_score"], 1 / 62 + 1 / 61)

    def test_item_in_both_lists_gets_two_contributions(self):
        result = reciprocal_rank_fusion(["A"], ["A"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["vector_rank"], 1)
        self.assertEqual(result[0]["fulltext_rank"], 1)
        self.assertAlmostEqual(result[0]["rrf_score"], 2 / 61)

    def test_custom_k_changes_weights(self):
        result = by_id(reciprocal_rank_fusion(["A"], [], k=1))
        self.assertAlmostEqual(result["A"]["rrf_score"], 1 / 2)

    def test_invalid_k(self):
        for k in (0, -1, 1.5, "60", True):
            with self.subTest(k=k), self.assertRaises(ValueError):
                reciprocal_rank_fusion(["A"], [], k=k)


class RRFOrderingTests(unittest.TestCase):
    def test_consensus_beats_single_list_top(self):
        # C está no topo só da lista vetorial; B aparece em 2º nas duas listas.
        result = reciprocal_rank_fusion(["C", "B"], ["D", "B"])
        self.assertEqual(result[0]["trecho_id"], "B")

    def test_sorted_by_score_descending(self):
        result = reciprocal_rank_fusion(["A", "B", "C"], ["C", "D"])
        scores = [item["rrf_score"] for item in result]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_ties_preserve_first_appearance_order(self):
        result = reciprocal_rank_fusion(["A", "B"], ["B", "A"])
        self.assertEqual([item["trecho_id"] for item in result], ["A", "B"])
        self.assertEqual(result[0]["rrf_score"], result[1]["rrf_score"])

    def test_single_list_keeps_its_order(self):
        # A função recebe só identificadores ordenados (sem scores brutos): com uma lista só,
        # a ordem de entrada é preservada.
        result = reciprocal_rank_fusion(["X", "Y", "Z"], [])
        self.assertEqual([item["trecho_id"] for item in result], ["X", "Y", "Z"])


class RRFRankBookkeepingTests(unittest.TestCase):
    def test_missing_rank_is_none(self):
        result = by_id(reciprocal_rank_fusion(["A"], ["B"]))
        self.assertEqual(result["A"]["fulltext_rank"], None)
        self.assertEqual(result["B"]["vector_rank"], None)
        self.assertEqual(set(result["A"]), {"trecho_id", "rrf_score", "vector_rank", "fulltext_rank"})

    def test_none_ids_are_skipped_without_consuming_rank(self):
        result = by_id(reciprocal_rank_fusion([None, "A"], []))
        self.assertEqual(result["A"]["vector_rank"], 1)
        self.assertNotIn(None, result)

    def test_duplicates_in_same_list_count_once(self):
        result = by_id(reciprocal_rank_fusion(["A", "A", "B"], []))
        self.assertAlmostEqual(result["A"]["rrf_score"], 1 / 61)
        self.assertEqual(result["B"]["vector_rank"], 2)

    def test_empty_inputs(self):
        self.assertEqual(reciprocal_rank_fusion([], []), [])

    def test_accepts_generators(self):
        result = reciprocal_rank_fusion((i for i in ["A"]), iter(["A"]))
        self.assertAlmostEqual(result[0]["rrf_score"], 2 / 61)


if __name__ == "__main__":
    unittest.main()
