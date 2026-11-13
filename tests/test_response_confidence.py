import unittest

from app.services.response_adapter import build_final_response, evidence_confidence


def sample_context():
    return {
        "chunks": [{
            "trecho_id": "TR-1",
            "registro_id": "REG-1",
            "fonte_id": "F-1",
            "url_fonte": "https://example.org/a",
            "texto": "Evidência",
            "identifier_matches": [],
            "graph_paths": [],
            "rrf_score": 1.0,
        }],
        "parameters": {
            "active_searches": ["vector", "fulltext"],
            "search_status": {"vector": "com_resultados", "fulltext": "com_resultados"},
            "rrf_max_score": 1.0,
        },
        "relationships": [],
        "nodes": [],
        "warnings": [],
        "cypher": "MATCH (t:Trecho) RETURN t",
    }


class EvidenceConfidenceTests(unittest.TestCase):
    def test_no_chunks_returns_no_evidence_not_low_confidence(self):
        context = sample_context()
        context["chunks"] = []
        result = evidence_confidence(context)
        self.assertEqual(result["level"], "Sem evidências")
        self.assertIn("probabilidade", result["disclaimer"])

    def test_single_record_is_low_and_explanation_is_explicit(self):
        result = evidence_confidence(sample_context())
        self.assertEqual(result["level"], "Baixa")
        self.assertIn("buscas vetorial e full-text", result["basis"][0])
        self.assertIn("Não é confiança estatística", result["disclaimer"])

    def test_multiple_independent_evidence_signals_raise_heuristic_level(self):
        context = sample_context()
        context["chunks"] = [
            {
                "trecho_id": f"TR-{i}",
                "registro_id": f"REG-{i}",
                "fonte_id": f"F-{1 if i < 3 else 2}",
                "identifier_matches": ["01340937000179"] if i == 1 else [],
                "graph_paths": ["Empresa -[APLICADA_A]-> Estabelecimento"] if i == 1 else [],
                "rrf_score": 1.0 - i / 10,
            }
            for i in range(1, 4)
        ]
        context["relationships"] = [{"type": "APLICADA_A"}]
        result = evidence_confidence(context)
        self.assertEqual(result["level"], "Alta")
        self.assertGreaterEqual(len(result["basis"]), 4)

    def test_partial_search_downgrades_the_heuristic_level(self):
        context = sample_context()
        context["chunks"] = [
            {
                "trecho_id": f"TR-{i}",
                "registro_id": f"REG-{i}",
                "fonte_id": f"F-{1 if i < 3 else 2}",
                "identifier_matches": ["01340937000179"] if i == 1 else [],
                "graph_paths": ["path"] if i == 1 else [],
                "rrf_score": 1.0 - i / 10,
            }
            for i in range(1, 4)
        ]
        context["relationships"] = [{"type": "APLICADA_A"}]
        context["parameters"]["active_searches"] = ["vector"]
        context["parameters"]["search_status"]["fulltext"] = "indisponivel"
        result = evidence_confidence(context)
        self.assertEqual(result["level"], "Moderada")
        self.assertTrue(any("rebaixado" in item for item in result["basis"]))

    def test_final_response_exposes_level_basis_and_disclaimer(self):
        result = build_final_response(sample_context(), "Resposta")
        self.assertIn(result["confidence_level"], {"Baixa", "Moderada", "Alta", "Sem evidências"})
        self.assertTrue(result["confidence_basis"])
        self.assertIn("não", result["confidence_disclaimer"].lower())


if __name__ == "__main__":
    unittest.main()
