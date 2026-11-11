import unittest

from app.services.response_adapter import build_final_response


class BuildFinalResponseTests(unittest.TestCase):
    def test_maps_and_deduplicates_sources_preserving_graph(self):
        context = {
            "chunks": [
                {"registro_id": "REG-1", "trecho_id": "TR-1", "texto": "Trecho oficial", "url_fonte": "https://example.org/1", "rrf_score": 0.8},
                {"registro_id": "REG-1", "trecho_id": "TR-2", "texto": "Outro trecho do mesmo registro", "url_fonte": None, "rrf_score": 0.5},
                {"registro_id": None, "trecho_id": "TR-3", "texto": "Trecho sem registro", "url_fonte": None, "rrf_score": 0.2},
            ],
            "parameters": {"rrf_max_score": 1.0},
            "cypher": "MATCH (n) RETURN n",
            "nodes": [{"id": "n1", "label": "Empresa", "properties": {}}],
            "relationships": [],
            "warnings": ["aviso do retrieval"],
        }
        result = build_final_response(context, "Resposta", additional_warnings=["aviso Dev1"])
        self.assertEqual(result["sources"], [
            {"id": "REG-1", "label": "Sancao", "url": "https://example.org/1", "excerpt": "Trecho oficial"},
            {"id": "TR-3", "label": "Trecho", "url": None, "excerpt": "Trecho sem registro"},
        ])
        self.assertEqual(result["nodes"], context["nodes"])
        self.assertEqual(result["relationships"], [])
        self.assertEqual(result["retrieval_relevance"], 0.8)
        self.assertFalse(result["abstained"])
        self.assertEqual(result["warnings"], ["aviso do retrieval", "aviso Dev1"])

    def test_empty_retrieval_defaults_to_abstention(self):
        result = build_final_response({"chunks": [], "parameters": {}, "cypher": "", "nodes": [], "relationships": [], "warnings": []}, "Não há evidências suficientes.")
        self.assertTrue(result["abstained"])
        self.assertIsNone(result["retrieval_relevance"])
        self.assertEqual(result["sources"], [])

    def test_dev1_can_override_abstention_decision(self):
        result = build_final_response({"chunks": [], "parameters": {}, "cypher": "", "nodes": [], "relationships": [], "warnings": []}, "Resposta", abstained=False)
        self.assertFalse(result["abstained"])


if __name__ == "__main__":
    unittest.main()
