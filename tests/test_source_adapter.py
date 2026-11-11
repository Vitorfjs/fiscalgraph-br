import unittest

from app.services.source_adapter import normalize_source


class NormalizeSourceTests(unittest.TestCase):
    def test_normalizes_final_contract(self):
        source = {
            "id": "REG-1",
            "label": "Sancao",
            "url": "https://example.org/1",
            "excerpt": "Trecho oficial",
        }
        self.assertEqual(normalize_source(source), source)

    def test_supports_legacy_mock_fixture(self):
        source = {
            "trecho_id": "TR-1",
            "registro_id": "REG-1",
            "fonte_id": "FONTE-1",
            "texto": "Trecho sintético",
            "url_fonte": "https://example.org/mock",
        }
        self.assertEqual(normalize_source(source), {
            "id": "FONTE-1",
            "label": "Sancao",
            "url": "https://example.org/mock",
            "excerpt": "Trecho sintético",
        })

    def test_supports_dev5_source_without_record_id(self):
        source = {"id": "TR-2", "label": "Trecho", "url": None, "excerpt": "Conteúdo"}
        self.assertEqual(normalize_source(source), source)


if __name__ == "__main__":
    unittest.main()
