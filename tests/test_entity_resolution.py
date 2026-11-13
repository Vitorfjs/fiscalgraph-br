import csv
import tempfile
import unittest
from pathlib import Path

from pipeline.text_to_graph.load_graph import (
    build_organization_index,
    organization_rows,
)


class OrganizationResolutionTests(unittest.TestCase):
    def _write_companies(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "empresas.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["cnpj_basico", "razao_social"])
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_exact_normalized_name_resolves_to_unique_cnpj_root(self):
        path = self._write_companies([
            {"cnpj_basico": "12345678", "razao_social": "Companhia Árvore Ltda."},
            {"cnpj_basico": "87654321", "razao_social": "Outra Organização S.A."},
        ])
        index = build_organization_index(path)
        item = {
            "trecho_id": "TR-1",
            "mencoes": [{
                "tipo": "ORGANIZACAO",
                "valor": "COMPANHIA ARVORE",
                "valor_normalizado": "COMPANHIA ARVORE",
                "inicio": 4,
                "fim": 19,
                "metodo": "spacy_ner_pt_core_news_sm",
            }],
        }
        rows = organization_rows(item, index)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cnpj_basico"], "12345678")
        self.assertEqual(rows[0]["inicio"], 4)
        self.assertEqual(rows[0]["fim"], 19)

    def test_normalization_collision_is_marked_ambiguous_and_not_linked(self):
        path = self._write_companies([
            {"cnpj_basico": "12345678", "razao_social": "ACME LTDA"},
            {"cnpj_basico": "87654321", "razao_social": "ACME S.A."},
        ])
        index = build_organization_index(path)
        self.assertIsNone(index["ACME"])
        item = {
            "trecho_id": "TR-2",
            "mencoes": [{
                "tipo": "ORGANIZACAO",
                "valor": "ACME",
                "valor_normalizado": "ACME",
                "inicio": 0,
                "fim": 4,
                "metodo": "spacy_ner_pt_core_news_sm",
            }],
        }
        self.assertEqual(organization_rows(item, index), [])

    def test_mention_without_exact_catalog_match_is_not_linked(self):
        path = self._write_companies([
            {"cnpj_basico": "12345678", "razao_social": "Empresa Alfa Ltda"},
        ])
        index = build_organization_index(path)
        item = {
            "trecho_id": "TR-3",
            "mencoes": [{
                "tipo": "ORGANIZACAO",
                "valor": "Empresa Beta",
                "inicio": 5,
                "fim": 17,
                "metodo": "spacy_ner_pt_core_news_sm",
            }],
        }
        self.assertEqual(organization_rows(item, index), [])


if __name__ == "__main__":
    unittest.main()
