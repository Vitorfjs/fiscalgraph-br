"""Testes do Text-to-Graph (dev4) usando somente dados sintéticos.

Executar na raiz do repositório:
    python -m unittest discover -s tests -p "test_text_to_graph.py" -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.text_to_graph.extractor import (  # noqa: E402
    CPF_MASK,
    build_chunk,
    compose_text,
    extract_mentions,
    mask_cpf,
    normalize_cnpj,
    process_csv,
    stable_id,
    structural_cnpj,
)
from pipeline.text_to_graph.load_graph import chunk_row, mention_rows, read_jsonl, summarize  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "compliance_sintetico.csv"


class _FakeEnt:
    def __init__(self, text, label, start, end):
        self.text, self.label_, self.start_char, self.end_char = text, label, start, end


class _FakeDoc:
    def __init__(self, ents):
        self.ents = ents


class FakeNLP:
    """Substitui o spaCy nos testes: reconhece termos fixos como ORG/LOC."""

    def __init__(self, terms):
        self.terms = terms

    def __call__(self, text):
        ents = []
        for term, label in self.terms:
            start = text.find(term)
            if start >= 0:
                ents.append(_FakeEnt(term, label, start, start + len(term)))
        return _FakeDoc(ents)


class CnpjTests(unittest.TestCase):
    def test_normalize_numeric_cnpj(self):
        self.assertEqual(normalize_cnpj("12.345.678/0001-90"), "12345678000190")
        self.assertTrue(structural_cnpj("12.345.678/0001-90"))

    def test_normalize_preserves_leading_zeros(self):
        self.assertEqual(normalize_cnpj("00.002.776/0001-40"), "00002776000140")

    def test_structural_alphanumeric_cnpj(self):
        # Fixture sintética: testa somente o formato, não dígitos verificadores.
        self.assertTrue(structural_cnpj("AB.CDE.FGH/01JK-23"))
        self.assertEqual(normalize_cnpj("ab.cde.fgh/01jk-23"), "ABCDEFGH01JK23")

    def test_reject_wrong_length(self):
        self.assertFalse(structural_cnpj("123"))
        self.assertFalse(structural_cnpj("123456780001901"))

    def test_reject_letters_in_check_digits(self):
        self.assertFalse(structural_cnpj("12345678000A9B"))


class MentionTests(unittest.TestCase):
    def test_extract_mention_span(self):
        text = "Registro ilustrativo para teste: 12.345.678/0001-90."
        found = extract_mentions(text)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["valor"], "12345678000190")
        self.assertEqual(found[0]["status"], "CANDIDATA")
        self.assertEqual(text[found[0]["inicio"]:found[0]["fim"]], "12.345.678/0001-90")

    def test_extract_alphanumeric_and_continuous(self):
        text = "Ficticio AB.CDE.FGH/01JK-23 e tambem 98765432000110."
        values = [m["valor"] for m in extract_mentions(text)]
        self.assertEqual(values, ["ABCDEFGH01JK23", "98765432000110"])

    def test_ignore_process_number_and_long_sequences(self):
        # 17 dígitos (número de processo) não é CNPJ; 15 dígitos também não.
        self.assertEqual(extract_mentions("Processo 00190107524201959 e 123456789012345"), [])

    def test_ignore_plain_words(self):
        # 14 letras/dígitos sem dígito nas 12 primeiras posições: palavra, não CNPJ.
        self.assertEqual(len("CODIGOEXEMPL12"), 14)
        self.assertEqual(extract_mentions("CODIGOEXEMPL12 ADMINISTRACA12"), [])

    def test_ignore_cpf(self):
        self.assertEqual(extract_mentions("CPF 123.456.789-09"), [])

    def test_ner_org_with_fake_nlp(self):
        text = "Empresa Ficticia Ltda foi citada em Sao Paulo."
        nlp = FakeNLP([("Empresa Ficticia Ltda", "ORG"), ("Sao Paulo", "LOC")])
        found = extract_mentions(text, nlp)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["tipo"], "ORGANIZACAO")
        self.assertEqual(found[0]["status"], "CANDIDATA")
        self.assertEqual(text[found[0]["inicio"]:found[0]["fim"]], "Empresa Ficticia Ltda")

    def test_ner_discards_noise(self):
        nlp = FakeNLP([("UN", "ORG"), ("123", "ORG"), ("DOU", "ORG")])
        self.assertEqual(extract_mentions("UN 123 publicado no DOU", nlp), [])

    def test_ner_ignores_uppercase_law_lines(self):
        # Linha em CAIXA ALTA (transcrição de lei) é descartada; linha mista é mantida.
        text = "Empresa Ficticia Ltda multada\nLEI 1 - ART. 2 - PODERA SER GARANTIDA A DEFESA"
        nlp = FakeNLP([("Empresa Ficticia Ltda", "ORG"), ("GARANTIDA", "ORG")])
        values = [m["valor"] for m in extract_mentions(text, nlp)]
        self.assertEqual(values, ["Empresa Ficticia Ltda"])

    def test_ner_keeps_uppercase_name_in_mixed_line(self):
        text = "Declarada inidonea a pessoa juridica FICTICIA ENGENHARIA S/A, conforme decisao."
        found = extract_mentions(text, FakeNLP([("FICTICIA ENGENHARIA S/A", "ORG")]))
        self.assertEqual([m["valor"] for m in found], ["FICTICIA ENGENHARIA S/A"])

    def test_mentions_sorted_by_position(self):
        text = "Org X cita 12.345.678/0001-90 depois."
        found = extract_mentions(text, FakeNLP([("Org X", "ORG")]))
        self.assertEqual([m["tipo"] for m in found], ["ORGANIZACAO", "CNPJ"])


class ChunkTests(unittest.TestCase):
    def _record(self, **overrides):
        record = {
            "registro_id": "R1", "fonte_id": "F1", "descricao": "Texto para teste",
            "observacoes": "", "fundamentacao_legal": "", "url_fonte": "https://example.invalid",
            "registro_origem": "arquivo.csv:2",
        }
        record.update(overrides)
        return record

    def test_build_chunk_keeps_provenance(self):
        chunk = build_chunk(self._record())
        self.assertIsNotNone(chunk)
        self.assertEqual(chunk["registro_id"], "R1")
        self.assertEqual(chunk["fonte_id"], "F1")
        self.assertEqual(chunk["url_fonte"], "https://example.invalid")
        self.assertEqual(chunk["registro_origem"], "arquivo.csv:2")
        self.assertEqual(chunk["metodo_extracao"], "regex_cnpj")

    def test_compose_text_uses_all_fields(self):
        text = compose_text(self._record(descricao="Multa", observacoes="Obs", fundamentacao_legal="Lei X"))
        self.assertEqual(text, "Multa\nObs\nLei X")

    def test_empty_record_returns_none(self):
        self.assertIsNone(build_chunk(self._record(descricao="")))

    def test_trecho_id_is_stable(self):
        a, b = build_chunk(self._record()), build_chunk(self._record())
        self.assertEqual(a["trecho_id"], b["trecho_id"])
        self.assertEqual(a["trecho_id"], stable_id("R1", "Texto para teste"))
        other = build_chunk(self._record(registro_id="R2"))
        self.assertNotEqual(a["trecho_id"], other["trecho_id"])

    def test_cpf_is_masked(self):
        text, count = mask_cpf("Responsavel 123.456.789-09.")
        self.assertEqual(count, 1)
        self.assertNotIn("123.456.789-09", text)
        self.assertIn(CPF_MASK, text)
        chunk = build_chunk(self._record(observacoes="CPF 123.456.789-09"))
        self.assertNotIn("123.456.789-09", chunk["texto"])
        self.assertEqual(chunk["cpf_mascarados"], 1)

    def test_spans_point_to_final_text(self):
        chunk = build_chunk(self._record(descricao="Multa", observacoes="Cita 12.345.678/0001-90"))
        m = chunk["mencoes"][0]
        self.assertEqual(chunk["texto"][m["inicio"]:m["fim"]], "12.345.678/0001-90")


class PipelineTests(unittest.TestCase):
    def test_process_fixture_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "trechos.jsonl"
            stats = process_csv(FIXTURE, out)
            items = list(read_jsonl(out))

        self.assertEqual(stats["registros_lidos"], 4)
        self.assertEqual(stats["registros_sem_texto"], 1)
        self.assertEqual(stats["trechos_gerados"], 3)
        self.assertEqual(stats["mencoes_por_tipo"], {"CNPJ": 3})
        self.assertEqual(stats["cnpjs_iguais_ao_sancionado"], 1)
        self.assertEqual(stats["cpf_mascarados"], 1)
        self.assertEqual(len(items), 3)

        dump = json.dumps(items, ensure_ascii=False)
        self.assertNotIn("123.456.789-09", dump)
        for item in items:
            self.assertTrue(item["registro_id"].startswith("R-SINT-"))
            self.assertEqual(item["fonte_id"], "F-SINT")
            for m in item["mencoes"]:
                self.assertEqual(m["status"], "CANDIDATA")
                self.assertEqual(normalize_cnpj(item["texto"][m["inicio"]:m["fim"]]), m["valor"])

    def test_missing_columns_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.csv"
            bad.write_text("registro_id,descricao\nR1,x\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                process_csv(bad, Path(tmp) / "out.jsonl")

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.jsonl", Path(tmp) / "b.jsonl"
            process_csv(FIXTURE, a)
            process_csv(FIXTURE, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())


class LoaderHelpersTests(unittest.TestCase):
    item = {
        "trecho_id": "T1", "registro_id": "R1", "fonte_id": "F1", "texto": "x",
        "url_fonte": "", "registro_origem": "", "metodo_extracao": "regex_cnpj",
        "mencoes": [
            {"tipo": "CNPJ", "valor": "12345678000190", "inicio": 0, "fim": 18, "metodo": "regex_cnpj_estrutural", "status": "CANDIDATA"},
            {"tipo": "ORGANIZACAO", "valor": "Org X", "inicio": 20, "fim": 25, "metodo": "spacy", "status": "CANDIDATA"},
        ],
    }

    def test_only_cnpj_mentions_become_links(self):
        rows = mention_rows(self.item)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cnpj"], "12345678000190")

    def test_chunk_row_serializes_mentions(self):
        row = chunk_row(self.item)
        self.assertEqual(len(json.loads(row["mencoes_json"])), 2)
        self.assertNotIn("mencoes", row)

    def test_summarize(self):
        self.assertEqual(summarize([self.item]), {"trechos": 1, "mencoes_cnpj": 1, "mencoes_org": 1})


if __name__ == "__main__":
    unittest.main()
