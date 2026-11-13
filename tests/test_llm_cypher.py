import json
import unittest
from unittest.mock import patch

from app.services.llm_cypher import (
    CypherSafetyError,
    DEFAULT_RESULT_ROWS,
    _extract_model_output,
    execute_read_only_cypher,
    generate_cypher,
    validate_read_only_cypher,
)


class CypherValidationTests(unittest.TestCase):
    def test_valid_graph_query_is_accepted_and_bounded(self):
        query = (
            "MATCH (e:Empresa)-[:POSSUI_ESTABELECIMENTO]->(est:Estabelecimento) "
            "RETURN e.razao_social AS empresa, est.uf AS uf"
        )
        validated = validate_read_only_cypher(query)
        self.assertIn(f"LIMIT {DEFAULT_RESULT_ROWS}", validated)

    def test_existing_limit_is_preserved(self):
        query = "MATCH (e:Empresa) RETURN e.cnpj_basico LIMIT 10"
        self.assertEqual(validate_read_only_cypher(query), query)

    def test_read_only_aggregation_is_allowed(self):
        query = "MATCH (s:Sancao) RETURN count(s) AS total LIMIT 20"
        self.assertEqual(validate_read_only_cypher(query), query)

    def test_write_clauses_are_rejected(self):
        for clause in ("CREATE (e:Empresa)", "MATCH (e:Empresa) SET e.porte = 'X' RETURN e",
                       "MATCH (e:Empresa) DETACH DELETE e"):
            with self.subTest(clause=clause), self.assertRaises(CypherSafetyError):
                validate_read_only_cypher(clause)

    def test_multiple_statements_and_comments_are_rejected(self):
        candidates = (
            "MATCH (e:Empresa) RETURN e.cnpj_basico; MATCH (s:Sancao) RETURN s.registro_id",
            "MATCH (e:Empresa) // comment\\nRETURN e",
            "MATCH (e:Empresa) /* comment */ RETURN e",
        )
        for query in candidates:
            with self.subTest(query=query), self.assertRaises(CypherSafetyError):
                validate_read_only_cypher(query)

    def test_unknown_labels_relationships_and_properties_are_rejected(self):
        candidates = (
            "MATCH (n:Usuario) RETURN n.nome",
            "MATCH (e:Empresa)-[:AMIGO_DE]->(x:Empresa) RETURN e.cnpj_basico",
            "MATCH (e:Empresa) RETURN e.senha",
        )
        for query in candidates:
            with self.subTest(query=query), self.assertRaises(CypherSafetyError):
                validate_read_only_cypher(query)

    def test_unbounded_or_excessive_variable_paths_are_rejected(self):
        candidates = (
            "MATCH p=(e:Empresa)-[*]->(x:Empresa) RETURN p",
            "MATCH p=(e:Empresa)-[*..7]->(x:Empresa) RETURN p",
        )
        for query in candidates:
            with self.subTest(query=query), self.assertRaises(CypherSafetyError):
                validate_read_only_cypher(query)

    def test_result_limit_is_bounded(self):
        for limit in (0, 101):
            with self.subTest(limit=limit), self.assertRaises(CypherSafetyError):
                validate_read_only_cypher(
                    f"MATCH (e:Empresa) RETURN e.cnpj_basico LIMIT {limit}"
                )

    def test_admin_namespaces_and_unknown_functions_are_rejected(self):
        candidates = (
            "MATCH (e:Empresa) RETURN apoc.cypher.run('RETURN 1', {})",
            "MATCH (e:Empresa) RETURN gds.pageRank(e)",
            "MATCH (e:Empresa) RETURN evilFunction(e)",
        )
        for query in candidates:
            with self.subTest(query=query), self.assertRaises(CypherSafetyError):
                validate_read_only_cypher(query)

    def test_unterminated_literal_is_rejected(self):
        with self.assertRaises(CypherSafetyError):
            validate_read_only_cypher("MATCH (e:Empresa) WHERE e.porte = 'ME RETURN e")

    def test_model_output_must_be_json_with_cypher(self):
        parsed = _extract_model_output(
            json.dumps({"cypher": "MATCH (e:Empresa) RETURN e.porte", "rationale": "consulta simples"})
        )
        self.assertIn("MATCH", parsed["cypher"])
        self.assertEqual(parsed["rationale"], "consulta simples")
        with self.assertRaises(CypherSafetyError):
            _extract_model_output('{"query": "MATCH (e:Empresa) RETURN e"}')


class LlmGenerationTests(unittest.TestCase):
    def test_generation_is_disabled_without_explicit_opt_in(self):
        env = {
            "LLM_CHAT_COMPLETIONS_URL": "https://llm.example/v1/chat/completions",
            "LLM_API_KEY": "secret",
            "LLM_MODEL": "test-model",
            "LLM_CYPHER_ENABLED": "false",
        }
        with patch.dict("os.environ", env, clear=True), patch(
            "urllib.request.urlopen"
        ) as urlopen:
            with self.assertRaises(RuntimeError):
                generate_cypher("Liste empresas.")
            urlopen.assert_not_called()

    def test_generation_sends_question_and_schema_not_retrieved_records(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "cypher": "MATCH (e:Empresa) RETURN e.cnpj_basico",
                                "rationale": "Consulta cadastral.",
                            })
                        }
                    }]
                }).encode("utf-8")

        env = {
            "LLM_CHAT_COMPLETIONS_URL": "https://llm.example/v1/chat/completions",
            "LLM_API_KEY": "secret",
            "LLM_MODEL": "test-model",
            "LLM_CYPHER_ENABLED": "true",
        }
        with patch.dict("os.environ", env, clear=True), patch(
            "urllib.request.urlopen", return_value=FakeResponse()
        ) as urlopen:
            generated = generate_cypher("Liste empresas cadastradas.")
        self.assertIn("LIMIT", generated["cypher"])
        request = urlopen.call_args.args[0]
        sent = json.loads(request.data.decode("utf-8"))
        self.assertIn("SCHEMA", sent["messages"][0]["content"])
        self.assertEqual(sent["messages"][1]["content"], "Liste empresas cadastradas.")
        self.assertNotIn("chunks", sent["messages"][1]["content"])


class ReadOnlyExecutionTests(unittest.TestCase):
    def test_explain_runs_before_query_and_records_are_bounded(self):
        class Summary:
            plan = {"operatorType": "NodeByLabelScan", "children": []}

        class Result:
            def __init__(self, rows=None):
                self._rows = rows or []

            def consume(self):
                return Summary()

            def data(self):
                return self._rows

        class Session:
            def __init__(self):
                self.calls = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def run(self, query):
                self.calls.append(query)
                return Result([{"total": 3}])

        class Driver:
            def __init__(self):
                self.active_session = Session()

            def session(self, database=None):
                return self.active_session

        driver = Driver()
        rows = execute_read_only_cypher(
            driver, "MATCH (e:Empresa) RETURN count(e) AS total"
        )
        self.assertEqual(rows, [{"total": 3}])
        self.assertTrue(driver.active_session.calls[0].startswith("EXPLAIN "))
        self.assertIn("MATCH", driver.active_session.calls[1])


if __name__ == "__main__":
    unittest.main()
