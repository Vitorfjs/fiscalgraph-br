import unittest
from unittest.mock import patch

from app.services.nl_cypher import QUERIES, run_constrained_cypher, validate_plan


class FakeResult:
    def data(self):
        return [{"registro_id": "CEIS-1"}]


class FakeTx:
    def __init__(self):
        self.calls = []

    def run(self, query, parameters=None):
        self.calls.append((query, parameters))
        return FakeResult()


class FakeSession:
    def __init__(self):
        self.tx = FakeTx()
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def execute_read(self, callback):
        return callback(self.tx)


class FakeDriver:
    def __init__(self):
        self.session_value = FakeSession()
        self.database_seen = None

    def session(self, database=None):
        self.database_seen = database
        return self.session_value


class NlCypherTests(unittest.TestCase):
    def test_validates_and_normalizes_cnpj(self):
        plan = validate_plan({
            "intent": "sancoes_por_cnpj",
            "cnpj": "01.340.937/0001-79",
            "limit": 5,
        })
        self.assertEqual(plan["parameters"]["cnpj"], "01340937000179")

    def test_rejects_unknown_intent(self):
        with self.assertRaises(ValueError):
            validate_plan({"intent": "create_node", "limit": 2})

    def test_rejects_invalid_cnpj(self):
        with self.assertRaises(ValueError):
            validate_plan({"intent": "empresa_por_cnpj", "cnpj": "123", "limit": 5})

    def test_rejects_out_of_range_limit(self):
        with self.assertRaises(ValueError):
            validate_plan({"intent": "listar_fontes", "limit": 100})

    def test_all_templates_are_read_only_and_parameterized(self):
        forbidden = ("CREATE ", "MERGE ", "DELETE ", "DETACH ", " SET ", "REMOVE ", "DROP ")
        for query in QUERIES.values():
            upper = query.upper()
            for keyword in forbidden:
                self.assertNotIn(keyword, upper)

    def test_disabled_by_default(self):
        class Retriever:
            driver = FakeDriver()
            database = "neo4j"
        with patch.dict("os.environ", {}, clear=True):
            result, warning = run_constrained_cypher("consulta", Retriever())
        self.assertIsNone(result)
        self.assertIsNone(warning)

    def test_requires_explicit_external_data_opt_in(self):
        class Retriever:
            driver = FakeDriver()
            database = "neo4j"
        with patch.dict("os.environ", {
            "LLM_CYPHER_ENABLED": "true", "LLM_SEND_EVIDENCE": "false",
        }, clear=True):
            result, warning = run_constrained_cypher("consulta", Retriever())
        self.assertIsNone(result)
        self.assertIn("desabilitado", warning)

    def test_executes_bound_query_in_read_transaction(self):
        driver = FakeDriver()
        class Retriever:
            database = "neo4j"
            def __init__(self):
                self.driver = driver
        plan = {"intent": "sancoes_por_cnpj",
                "cnpj": "01340937000179", "limit": 5}
        with patch.dict("os.environ", {
            "LLM_CYPHER_ENABLED": "true", "LLM_SEND_EVIDENCE": "true",
        }, clear=True), patch("app.services.nl_cypher._request_plan", return_value=plan):
            result, warning = run_constrained_cypher("consulta", Retriever())
        self.assertIsNone(warning)
        self.assertEqual(result["rows"], [{"registro_id": "CEIS-1"}])
        query, params = driver.session_value.tx.calls[0]
        self.assertIn("$cnpj", query)
        self.assertNotIn("01340937000179", query)
        self.assertEqual(params["cnpj"], "01340937000179")
        self.assertTrue(driver.session_value.closed)
        self.assertEqual(driver.database_seen, "neo4j")


if __name__ == "__main__":
    unittest.main()
