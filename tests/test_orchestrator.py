import io
import json
import urllib.error
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


def valid_context(
    with_chunk=True,
    *,
    query="sanção documental",
    vector_status="com_resultados",
    fulltext_status="com_resultados",
    query_identifiers=None,
    chunks_override=None,
    nodes_override=None,
    warnings_override=None,
):
    chunks = []
    nodes = []
    if with_chunk:
        v_rank = 1 if vector_status == "com_resultados" else None
        f_rank = 1 if fulltext_status == "com_resultados" else None
        rrf_score = (1.0 / (60 + v_rank) if v_rank else 0.0) + (1.0 / (60 + f_rank) if f_rank else 0.0)
        chunks = chunks_override if chunks_override is not None else [{
            "trecho_id": "TR-1",
            "texto": "Trecho documental sintético sobre uma sanção.",
            "registro_id": "REG-1",
            "fonte_id": "F-1",
            "url_fonte": "https://example.org/doc",
            "vector_rank": v_rank,
            "fulltext_rank": f_rank,
            "vector_score": 0.9 if v_rank else None,
            "fulltext_score": 2.0 if f_rank else None,
            "rrf_score": rrf_score,
            "graph_paths": [],
            "identifier_matches": [],
        }]
        nodes = nodes_override if nodes_override is not None else [
            {"id": "Trecho:TR-1", "label": "Trecho", "properties": {"trecho_id": "TR-1"}}
        ]
    else:
        vector_status = "sem_resultados"
        fulltext_status = "sem_resultados"

    search_status = {"vector": vector_status, "fulltext": fulltext_status}
    active_searches = [name for name, state in search_status.items() if state == "com_resultados"]
    default_warnings = [] if with_chunk else ["Nenhum trecho foi recuperado."]

    return {
        "query": query,
        "retrieval_mode": "hybrid",
        "chunks": chunks,
        "nodes": nodes,
        "relationships": [],
        "cypher": "MATCH (t:Trecho) RETURN t",
        "warnings": list(warnings_override) if warnings_override is not None else default_warnings,
        "parameters": {
            "top_k": 5,
            "candidate_k": 20,
            "rrf_k": 60,
            "rrf_max_score": float(2 / 61),
            "active_searches": active_searches,
            "search_status": search_status,
            "query_identifiers": list(query_identifiers or []),
        },
    }


class FakeHttpResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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
        retriever = FakeRetriever(valid_context(with_chunk=False, query="consulta sem resultados"))
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

    def test_out_of_domain_query_with_vector_only_chunks_abstains(self):
        context = valid_context(
            query="receita de bolo de chocolate",
            vector_status="com_resultados",
            fulltext_status="sem_resultados",
            warnings_override=[
                "Nenhum termo da pergunta aparece nos trechos indexados; os resultados vêm só da similaridade semântica e podem ter baixa relevância."
            ],
        )
        retriever = FakeRetriever(context)
        llm_env = {
            "LLM_CHAT_COMPLETIONS_URL": "https://llm.example/v1/chat/completions",
            "LLM_API_KEY": "secret-key",
            "LLM_MODEL": "test-model",
            "LLM_SEND_EVIDENCE": "true",
        }
        with patch.dict("os.environ", llm_env, clear=True), patch("urllib.request.urlopen") as mock_open:
            result = answer_question("receita de bolo de chocolate", retriever=retriever)
        mock_open.assert_not_called()
        self.assertTrue(result["abstained"])
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["relationships"], [])
        self.assertIsNone(result["retrieval_relevance"])
        self.assertIn("fora do escopo", result["answer"].lower())
        self.assertTrue(any("fora do domínio" in w.lower() or "fora do escopo" in w.lower() for w in result["warnings"]))

    def test_unsearchable_query_without_fulltext_terms_abstains(self):
        context = valid_context(
            query="o que é isso?",
            vector_status="com_resultados",
            fulltext_status="nao_executada",
            warnings_override=["A pergunta não gerou termos para a busca full-text; resultado apenas vetorial."],
        )
        retriever = FakeRetriever(context)
        with patch.dict("os.environ", {}, clear=True):
            result = answer_question("o que é isso?", retriever=retriever)
        self.assertTrue(result["abstained"])
        self.assertTrue(any("insuficiente" in w.lower() or "termos" in w.lower() for w in result["warnings"]))

    def test_literal_cnpj_not_matched_in_chunks_or_nodes_abstains(self):
        context = valid_context(
            query="Quais sanções existem para o CNPJ 99.999.999/0001-99?",
            query_identifiers=["99999999000199"],
            chunks_override=[{
                "trecho_id": "TR-1",
                "texto": "Sanção aplicada à empresa 01.340.937/0001-79.",
                "registro_id": "CEIS-289814",
                "fonte_id": "F-CGU-CEIS",
                "url_fonte": "https://example.org/ceis",
                "vector_rank": 1,
                "fulltext_rank": 1,
                "vector_score": 0.85,
                "fulltext_score": 1.2,
                "rrf_score": float(2 / 61),
                "graph_paths": [],
                "identifier_matches": [],
            }],
            nodes_override=[
                {"id": "Trecho:TR-1", "label": "Trecho", "properties": {"trecho_id": "TR-1"}},
                {"id": "Estabelecimento:01340937000179", "label": "Estabelecimento", "properties": {"cnpj": "01340937000179"}},
            ],
        )
        retriever = FakeRetriever(context)
        with patch.dict("os.environ", {}, clear=True):
            result = answer_question("Quais sanções existem para o CNPJ 99.999.999/0001-99?", retriever=retriever)
        self.assertTrue(result["abstained"])
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["relationships"], [])
        self.assertIsNone(result["retrieval_relevance"])
        self.assertIn("99999999000199", result["answer"])
        self.assertTrue(any("99999999000199" in w for w in result["warnings"]))

    def test_literal_cnpj_matched_in_second_chunk_is_prioritized_in_answer(self):
        chunks = [
            {
                "trecho_id": "TR-1",
                "texto": "Outro registro sem o CNPJ buscado.",
                "registro_id": "CEIS-111",
                "fonte_id": "F-CGU-CEIS",
                "url_fonte": "https://example.org/1",
                "vector_rank": 1,
                "fulltext_rank": 2,
                "vector_score": 0.9,
                "fulltext_score": 1.0,
                "rrf_score": float(1 / 61 + 1 / 62),
                "graph_paths": [],
                "identifier_matches": [],
            },
            {
                "trecho_id": "TR-2",
                "texto": "Multa para o CNPJ 01.340.937/0001-79.",
                "registro_id": "CEIS-289814",
                "fonte_id": "F-CGU-CEIS",
                "url_fonte": "https://example.org/2",
                "vector_rank": 2,
                "fulltext_rank": 1,
                "vector_score": 0.8,
                "fulltext_score": 3.0,
                "rrf_score": float(1 / 62 + 1 / 61),
                "graph_paths": [],
                "identifier_matches": ["01340937000179"],
            },
        ]
        context = valid_context(
            query="trecho que cita o CNPJ 01.340.937/0001-79",
            query_identifiers=["01340937000179"],
            chunks_override=chunks,
        )
        retriever = FakeRetriever(context)
        with patch.dict("os.environ", {}, clear=True):
            result = answer_question("trecho que cita o CNPJ 01.340.937/0001-79", retriever=retriever)
        self.assertFalse(result["abstained"])
        self.assertIn("CEIS-289814", result["answer"])
        self.assertLess(result["answer"].index("CEIS-289814"), result["answer"].index("CEIS-111"))

    def test_partial_search_unavailability_informs_limitation_without_abstaining(self):
        context = valid_context(
            query="empresa inidônea",
            vector_status="indisponivel",
            fulltext_status="com_resultados",
            warnings_override=["Busca vetorial indisponível no índice trecho_embedding_vector; resultado apenas full-text"],
        )
        retriever = FakeRetriever(context)
        with patch.dict("os.environ", {}, clear=True):
            result = answer_question("empresa inidônea", retriever=retriever)
        self.assertFalse(result["abstained"])
        self.assertTrue(any("apenas a modalidade fulltext" in w.lower() or "indisponível" in w.lower() for w in result["warnings"]))

    def test_domain_query_with_vector_only_results_warns_insufficiency_and_presents_evidence(self):
        context = valid_context(
            query="quais empresas receberam penalidade contratual?",
            vector_status="com_resultados",
            fulltext_status="sem_resultados",
            warnings_override=[
                "Nenhum termo da pergunta aparece nos trechos indexados; os resultados vêm só da similaridade semântica e podem ter baixa relevância."
            ],
        )
        retriever = FakeRetriever(context)
        with patch.dict("os.environ", {}, clear=True):
            result = answer_question("quais empresas receberam penalidade contratual?", retriever=retriever)
        self.assertFalse(result["abstained"])
        self.assertIn("REG-1", result["answer"])
        self.assertTrue(any("apenas a busca vetorial" in w.lower() or "insuficiente" in w.lower() for w in result["warnings"]))

    def test_llm_opt_in_disabled_never_calls_external_endpoint(self):
        retriever = FakeRetriever(valid_context())
        env = {
            "LLM_CHAT_COMPLETIONS_URL": "https://llm.example/v1/chat/completions",
            "LLM_API_KEY": "super-secret-token",
            "LLM_MODEL": "test-model",
            "LLM_SEND_EVIDENCE": "false",
        }
        with patch.dict("os.environ", env, clear=True), patch("urllib.request.urlopen") as mock_open:
            result = answer_question("sanção documental", retriever=retriever)
        mock_open.assert_not_called()
        self.assertFalse(result["abstained"])
        self.assertTrue(any("desabilitado" in w.lower() for w in result["warnings"]))
        self.assertNotIn("super-secret-token", result["answer"] + " ".join(result["warnings"]))

    def test_llm_grounded_response_is_returned_when_enabled(self):
        retriever = FakeRetriever(valid_context())
        env = {
            "LLM_CHAT_COMPLETIONS_URL": "https://llm.example/v1/chat/completions",
            "LLM_API_KEY": "super-secret-token",
            "LLM_MODEL": "test-model",
            "LLM_SEND_EVIDENCE": "true",
        }
        llm_payload = {
            "choices": [{"message": {"content": "O registro REG-1 descreve uma sanção documental."}}]
        }
        with patch.dict("os.environ", env, clear=True), patch(
            "urllib.request.urlopen", return_value=FakeHttpResponse(llm_payload)
        ) as mock_open:
            result = answer_question("sanção documental", retriever=retriever)
        mock_open.assert_called_once()
        self.assertFalse(result["abstained"])
        self.assertEqual(result["answer"], "O registro REG-1 descreve uma sanção documental.")
        self.assertFalse(any("LLM não configurado" in w for w in result["warnings"]))

    def test_llm_errors_and_empty_or_malformed_responses_fallback_safely(self):
        retriever = FakeRetriever(valid_context())
        env = {
            "LLM_CHAT_COMPLETIONS_URL": "https://llm.example/v1/chat/completions",
            "LLM_API_KEY": "super-secret-token",
            "LLM_MODEL": "test-model",
            "LLM_SEND_EVIDENCE": "true",
        }
        cases = [
            TimeoutError("timed out"),
            urllib.error.HTTPError("https://llm.example", 401, "Unauthorized", {}, io.BytesIO(b"secret leak")),
            FakeHttpResponse({"choices": [{"message": {"content": "   "}}]}),
            FakeHttpResponse({"unexpected": "schema"}),
        ]
        for side_effect in cases:
            with self.subTest(case=repr(side_effect)):
                with patch.dict("os.environ", env, clear=True), patch(
                    "urllib.request.urlopen", side_effect=side_effect if isinstance(side_effect, Exception) else None,
                    return_value=None if isinstance(side_effect, Exception) else side_effect,
                ):
                    result = answer_question("sanção documental", retriever=retriever)
                self.assertIn("REG-1", result["answer"])
                self.assertTrue(any("determinística" in w.lower() for w in result["warnings"]))
                self.assertNotIn("super-secret-token", " ".join(result["warnings"]))

    def test_llm_invented_identifier_is_rejected_and_falls_back_to_deterministic(self):
        retriever = FakeRetriever(valid_context())
        env = {
            "LLM_CHAT_COMPLETIONS_URL": "https://llm.example/v1/chat/completions",
            "LLM_API_KEY": "super-secret-token",
            "LLM_MODEL": "test-model",
            "LLM_SEND_EVIDENCE": "true",
        }
        llm_payload = {
            "choices": [{"message": {"content": "Conforme o registro CEIS-999999 e o CNPJ 88.888.888/0001-88, houve fraude."}}]
        }
        with patch.dict("os.environ", env, clear=True), patch(
            "urllib.request.urlopen", return_value=FakeHttpResponse(llm_payload)
        ):
            result = answer_question("sanção documental", retriever=retriever)
        self.assertNotIn("CEIS-999999", result["answer"])
        self.assertNotIn("88.888.888/0001-88", result["answer"])
        self.assertIn("REG-1", result["answer"])
        self.assertTrue(any("identificador" in w.lower() or "rastreável" in w.lower() for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
