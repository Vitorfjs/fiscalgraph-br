import unittest

from app.services.mock_service import get_mock_response


class MockServiceTests(unittest.TestCase):
    def test_complete_fixture_is_available_and_has_graph(self):
        payload = get_mock_response("sucesso")
        self.assertFalse(payload["abstained"])
        self.assertTrue(payload["sources"])
        self.assertTrue(payload["nodes"])
        self.assertIsInstance(payload["relationships"], list)
        self.assertTrue(any("sintética" in warning.lower() for warning in payload["warnings"]))

    def test_abstention_fixture_is_available_and_empty(self):
        payload = get_mock_response("abstencao")
        self.assertTrue(payload["abstained"])
        self.assertEqual(payload["sources"], [])
        self.assertEqual(payload["nodes"], [])
        self.assertEqual(payload["relationships"], [])
        self.assertTrue(payload["warnings"])


if __name__ == "__main__":
    unittest.main()
