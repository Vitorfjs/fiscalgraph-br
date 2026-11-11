import unittest
from unittest.mock import patch

from app.services.orchestrator import answer_question


class FakeRetriever:
    def __init__(self, context):
        self.context = context
        self.calls = []
        self.closed = False

    def retrieve_context(self, question, top_k=5):
        self.calls.append((question, top_k))
        return self.context

    def close(self):
        self.closed = True


def valid_context(with_chunk=True):
    chunks = []
    nodes = []
    if with_chunk:
        chunks = [{
            "trecho_id": "TR-1", "texto": "Trecho documental sintético sobre uma sanção.",
            "registro_id": "REG-1", "fonte_id": "F-1", "url_fonte": "https://example.org/doc",
            "vector_rank": 1, "fulltext_rank": 1, "vector_score": 0.9, "fulltext_score": 2.0,
            "rrf_score": float(1 / 61 + 1 / 61), "graph_paths": [], "identifier_matches": [],
        }]
        nodes = [{"id": "Trecho:TR-1", "label": "Trecho", "properties": {"trecho_id": "TR-1"}}]
    return {
        "query": "sanção documental", "retrieval_mode": "hybrid", "chunks": chunks,
        "nodes": nodes, "relationships": [], "cypher": "MATCH (t:Trecho) RETURN t",
        "warnings": [] if with_chunk else ["Nenhum trecho foi recuperado."],
        "parameters": {
            "top_k": 5, "candidate_k": 20, "rrf_k": 60, "rrf_max_score": float(2 / 61),
            "active_searches": ["vector", "fulltext"] if with_chunk else [],
            "search_status": {"vector": "com_resultados", "fulltext": "com_resultados"} if with_chunk else {"vector": "sem_resultados", "fulltext": "sem_resultados"},
            "query_identifiers": [],
        },
    }


class OrchestratorTests(unittest.TestCase):
    def test_runs_retrieval_and_builds_final_contract_without_llm(self):
        retriever = FakeRetriever(valid_context())
        with patch.dict("os.environ", {}, clear=True):
            result = answer_question("sanção documental", top_k=3, retriever=retriever)
        self.assertEqual(retriever.calls, [("sanção documental", 3)])
        self.assertFalse(result["abstained"])
        self.assertEqual(result["sources"][0]["id"], "REG-1")
        self.assertIn("excerpt", result["sources"][0])
        self.assertTrue(any("LLM não configurado" in w for w in result["warnings"]))

    def test_empty_retrieval_abstains_without_llm(self):
        retriever = FakeRetriever(valid_context(with_chunk=False))
        with patch.dict("os.environ", {}, clear=True):
            result = answer_question("consulta sem resultados", retriever=retriever)
        self.assertTrue(result["abstained"])
        self.assertEqual(result["sources"], [])
        self.assertIn("não encontrei trechos", result["answer"].lower())

    def test_invalid_retrieval_contract_is_rejected(self):
        context = valid_context()
        del context["parameters"]["query_identifiers"]
        retriever = FakeRetriever(context)
        with self.assertRaisesRegex(ValueError, "fora do contrato"):
            answer_question("sanção documental", retriever=retriever)


if __name__ == "__main__":
    unittest.main()
