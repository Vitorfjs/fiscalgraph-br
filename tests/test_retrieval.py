"""Testes do serviço de recuperação híbrida (dev5) com driver e encoder falsos.

Não exigem Neo4j, torch nem download de modelo. Todos os dados abaixo são sintéticos.

Executar na raiz do repositório:
    python -m unittest discover -s tests -p "test_retrieval.py" -v
"""
import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services import embeddings, retrieval  # noqa: E402
from app.services.contract import validate_retrieval_response  # noqa: E402
from app.services.retrieval import (  # noqa: E402
    CANDIDATE_MULTIPLIER,
    FULLTEXT_INDEX,
    MAX_TOP_K,
    MENCIONA_WARNING,
    MIN_CANDIDATES,
    NO_EVIDENCE_WARNING,
    GraphHybridRetriever,
    build_fulltext_query,
)

CONTRACT_CHUNK_KEYS = {
    "trecho_id", "texto", "registro_id", "fonte_id", "url_fonte",
    "vector_rank", "fulltext_rank", "rrf_score",
}


# --------------------------------------------------------------------------- grafo sintético
def node(element_id, labels, **properties):
    return {"element_id": element_id, "labels": list(labels), "properties": properties}


def rel(element_id, rel_type, start, end, **properties):
    return {"element_id": element_id, "type": rel_type, "start": start["element_id"],
            "end": end["element_id"], "properties": properties}


def path(nodes, relationships):
    return {"nodes": nodes, "relationships": relationships}


T1 = node("n:t1", ["Trecho"], trecho_id="T1", registro_id="SINT-CEIS-1", fonte_id="F-SINT",
          url_fonte="https://exemplo.invalid/ceis", metodo_extracao="regex_cnpj", embedding=None)
T2 = node("n:t2", ["Trecho"], trecho_id="T2", registro_id="", fonte_id="", url_fonte="")
FONTE = node("n:f", ["Fonte"], fonte_id="F-SINT", nome="Fonte sintética", url="https://exemplo.invalid/fonte")
SANCAO = node("n:s", ["Sancao"], registro_id="SINT-CEIS-1", tipo_registro="CEIS",
              observacoes="texto longo que não deve sair", cnpj_sancionado="SINT0000000100")
SANCAO2 = node("n:s2", ["Sancao"], registro_id="SINT-CEIS-2", tipo_registro="CEIS")
EST = node("n:est", ["Estabelecimento"], cnpj="SINT0000000100", cnpj_basico="SINT0000", uf="SP")
EMP = node("n:emp", ["Empresa"], cnpj_basico="SINT0000", razao_social="EMPRESA SINTETICA", capital_social="1")
SOCIO_PF = node("n:sf", ["Socio"], socio_id="SOC-PF", nome="PESSOA SINTETICA", tipo_pessoa="PESSOA FISICA")
SOCIO_PJ = node("n:sj", ["Socio"], socio_id="SOC-PJ", nome="HOLDING SINTETICA", tipo_pessoa="PESSOA JURIDICA")

R_FONTE = rel("r:of", "ORIGINADO_DE", T1, FONTE)
R_EXTRATO = rel("r:ex", "EXTRATO_DE", T1, SANCAO)
R_APLICADA = rel("r:ap", "APLICADA_A", SANCAO, EST, registro_origem="SINT:L1")
R_POSSUI = rel("r:po", "POSSUI_ESTABELECIMENTO", EMP, EST)
R_PF = rel("r:pf", "PARTICIPA_DE", SOCIO_PF, EMP, qualificacao="Sócio")
R_PJ = rel("r:pj", "PARTICIPA_DE", SOCIO_PJ, EMP, qualificacao="Sócio")
R_MENCIONA = rel("r:me", "MENCIONA", T1, EST, status="CANDIDATA", inicio=10, fim=28)
R2_FONTE = rel("r2:of", "ORIGINADO_DE", T2, FONTE)
R2_EXTRATO = rel("r2:ex", "EXTRATO_DE", T2, SANCAO2)

EXPANSION = {
    "T1": {
        "trecho_id": "T1", "texto": "Texto sintético do trecho 1", "trecho": T1,
        "paths": [  # prefixos, como a consulta de expansão devolve
            path([T1, FONTE], [R_FONTE]),
            path([T1, SANCAO], [R_EXTRATO]),
            path([T1, SANCAO, EST], [R_EXTRATO, R_APLICADA]),
            path([T1, SANCAO, EST, EMP], [R_EXTRATO, R_APLICADA, R_POSSUI]),
            path([T1, SANCAO, EST, EMP, SOCIO_PF], [R_EXTRATO, R_APLICADA, R_POSSUI, R_PF]),
            path([T1, SANCAO, EST, EMP, SOCIO_PJ], [R_EXTRATO, R_APLICADA, R_POSSUI, R_PJ]),
            path([T1, EST], [R_MENCIONA]),
        ],
    },
    "T2": {
        "trecho_id": "T2", "texto": "Texto sintético do trecho 2", "trecho": T2,
        "paths": [path([T2, FONTE], [R2_FONTE]), path([T2, SANCAO2], [R2_EXTRATO])],
    },
}


class FakeSession:
    def __init__(self, vector, fulltext, expansion=EXPANSION):
        self.vector, self.fulltext, self.expansion = vector, fulltext, expansion
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, parameters=None, **kwargs):
        params = dict(parameters or {}, **kwargs)
        self.calls.append((query, params))
        if "db.index.vector.queryNodes" in query:
            return self._rows(self.vector)
        if "db.index.fulltext.queryNodes" in query:
            return self._rows(self.fulltext)
        if "UNWIND $trecho_ids" in query:
            return [self.expansion[tid] for tid in params["trecho_ids"] if tid in self.expansion]
        raise AssertionError(f"consulta inesperada: {query}")

    @staticmethod
    def _rows(spec):
        if isinstance(spec, Exception):
            raise spec
        return [{"trecho_id": tid, "score": score} for tid, score in spec]

    def queries(self, fragment):
        return [params for query, params in self.calls if fragment in query]


class FakeDriver:
    def __init__(self, session):
        self._session = session
        self.databases = []

    def session(self, database=None):
        self.databases.append(database)
        return self._session


class FakeEncoder:
    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        return [[0.0] * embeddings.EMBEDDING_DIMENSIONS for _ in texts]


def run(vector, fulltext, question="sanção sintética de inidoneidade", top_k=5):
    session = FakeSession(vector, fulltext)
    retriever = GraphHybridRetriever(FakeDriver(session), FakeEncoder())
    return retriever.retrieve_context(question, top_k), session


# --------------------------------------------------------------------------- testes
class ContractTests(unittest.TestCase):
    def test_response_shape_matches_contract(self):
        result, _ = run([("T2", 0.9), ("T1", 0.8)], [("T1", 3.0)])
        self.assertEqual(result["query"], "sanção sintética de inidoneidade")
        self.assertEqual(result["retrieval_mode"], "hybrid")
        self.assertIsInstance(result["cypher"], str)
        self.assertIsInstance(result["warnings"], list)
        for chunk in result["chunks"]:
            self.assertTrue(CONTRACT_CHUNK_KEYS <= set(chunk))
            self.assertIsInstance(chunk["trecho_id"], str)
            self.assertIsInstance(chunk["texto"], str)
            self.assertIsInstance(chunk["rrf_score"], float)
        for item in result["nodes"]:
            self.assertEqual(set(item), {"id", "label", "properties"})
        for item in result["relationships"]:
            self.assertEqual(set(item), {"source", "target", "type", "properties"})

    def test_chunks_follow_rrf_and_keep_both_ranks(self):
        result, _ = run([("T2", 0.9), ("T1", 0.8)], [("T1", 3.0)])
        first, second = result["chunks"]
        self.assertEqual((first["trecho_id"], first["vector_rank"], first["fulltext_rank"]), ("T1", 2, 1))
        self.assertAlmostEqual(first["rrf_score"], 1 / 62 + 1 / 61)
        self.assertEqual((second["trecho_id"], second["vector_rank"], second["fulltext_rank"]), ("T2", 1, None))
        # Scores brutos são informativos e ficam separados do rrf_score.
        self.assertEqual((first["vector_score"], first["fulltext_score"]), (0.8, 3.0))

    def test_top_k_cuts_after_fusion(self):
        result, _ = run([("T2", 0.9), ("T1", 0.8)], [("T1", 3.0)], top_k=1)
        self.assertEqual([c["trecho_id"] for c in result["chunks"]], ["T1"])

    def test_candidate_pool_is_larger_than_top_k(self):
        _, session = run([("T1", 0.8)], [("T1", 3.0)], top_k=2)
        expected = max(2 * CANDIDATE_MULTIPLIER, MIN_CANDIDATES)
        self.assertEqual(session.queries("vector.queryNodes")[0]["limit"], expected)
        self.assertEqual(session.queries("fulltext.queryNodes")[0]["limit"], expected)

    def test_uses_integrated_index_names(self):
        _, session = run([("T1", 0.8)], [("T1", 3.0)])
        self.assertEqual(session.queries("vector.queryNodes")[0]["index_name"], "trecho_embedding_vector")
        self.assertEqual(session.queries("fulltext.queryNodes")[0]["index_name"], "fiscalgraph_text_fulltext")
        self.assertTrue(session.queries("fulltext.queryNodes")[0]["query"].startswith("texto:("))


class ProvenanceTests(unittest.TestCase):
    def test_provenance_comes_from_trecho(self):
        result, _ = run([("T1", 0.8)], [])
        chunk = result["chunks"][0]
        self.assertEqual(chunk["registro_id"], "SINT-CEIS-1")
        self.assertEqual(chunk["fonte_id"], "F-SINT")
        self.assertEqual(chunk["url_fonte"], "https://exemplo.invalid/ceis")

    def test_blank_trecho_fields_fall_back_to_linked_nodes(self):
        result, _ = run([("T2", 0.8)], [])
        chunk = result["chunks"][0]
        self.assertEqual(chunk["registro_id"], "SINT-CEIS-2")
        self.assertEqual(chunk["fonte_id"], "F-SINT")
        self.assertEqual(chunk["url_fonte"], "https://exemplo.invalid/fonte")


class GraphExpansionTests(unittest.TestCase):
    def setUp(self):
        self.result, _ = run([("T1", 0.8)], [("T1", 2.0)])
        self.nodes = {n["id"]: n for n in self.result["nodes"]}

    def test_reaches_all_expected_labels_with_stable_ids(self):
        self.assertEqual(set(self.nodes), {
            "Trecho:T1", "Fonte:F-SINT", "Sancao:SINT-CEIS-1", "Estabelecimento:SINT0000000100",
            "Empresa:SINT0000", "Socio:SOC-PF", "Socio:SOC-PJ",
        })

    def test_node_properties_are_minimal(self):
        for item in self.result["nodes"]:
            self.assertFalse({"embedding", "texto", "mencoes_json"} & set(item["properties"]), item["id"])
        self.assertNotIn("observacoes", self.nodes["Sancao:SINT-CEIS-1"]["properties"])
        self.assertNotIn("capital_social", self.nodes["Empresa:SINT0000"]["properties"])

    def test_person_partner_name_is_not_returned(self):
        self.assertNotIn("nome", self.nodes["Socio:SOC-PF"]["properties"])
        self.assertEqual(self.nodes["Socio:SOC-PJ"]["properties"]["nome"], "HOLDING SINTETICA")

    def test_relationships_are_unique_and_keep_direction(self):
        rels = self.result["relationships"]
        self.assertEqual(len(rels), 7)  # 9 ocorrências nos prefixos, 7 relacionamentos distintos
        socio_rel = next(r for r in rels if r["source"] == "Socio:SOC-PF")
        self.assertEqual((socio_rel["type"], socio_rel["target"]), ("PARTICIPA_DE", "Empresa:SINT0000"))
        aplicada = next(r for r in rels if r["type"] == "APLICADA_A")
        self.assertEqual(aplicada["properties"], {"registro_origem": "SINT:L1"})

    def test_graph_paths_are_maximal_and_readable(self):
        paths = self.result["chunks"][0]["graph_paths"]
        self.assertEqual(len(paths), 4)  # Fonte, Sócio PF, Sócio PJ, MENCIONA
        self.assertIn(
            "(Trecho:T1)-[:EXTRATO_DE]->(Sancao:SINT-CEIS-1)-[:APLICADA_A]->(Estabelecimento:SINT0000000100)"
            "<-[:POSSUI_ESTABELECIMENTO]-(Empresa:SINT0000)<-[:PARTICIPA_DE]-(Socio:SOC-PF)",
            paths,
        )

    def test_menciona_is_flagged_as_candidate(self):
        self.assertIn(MENCIONA_WARNING, self.result["warnings"])


class WarningAndFallbackTests(unittest.TestCase):
    def test_no_results_returns_empty_lists_and_clear_warning(self):
        result, session = run([], [])
        self.assertEqual((result["chunks"], result["nodes"], result["relationships"]), ([], [], []))
        self.assertIn(NO_EVIDENCE_WARNING, result["warnings"])
        self.assertTrue(any("nenhum Trecho possui embedding" in w for w in result["warnings"]))
        self.assertEqual(session.queries("UNWIND $trecho_ids"), [])

    def test_missing_vector_index_falls_back_to_fulltext(self):
        error = retrieval._Neo4jClientError("There is no such vector schema index")
        result, _ = run(error, [("T1", 2.0)])
        self.assertEqual([c["trecho_id"] for c in result["chunks"]], ["T1"])
        self.assertIsNone(result["chunks"][0]["vector_rank"])
        self.assertTrue(any("Busca vetorial indisponível" in w for w in result["warnings"]))
        self.assertFalse(any("nenhum Trecho possui embedding" in w for w in result["warnings"]))

    def test_missing_fulltext_index_falls_back_to_vector(self):
        error = retrieval._Neo4jClientError("There is no such fulltext schema index")
        result, _ = run([("T1", 0.8)], error)
        self.assertEqual([c["trecho_id"] for c in result["chunks"]], ["T1"])
        self.assertTrue(any("Busca full-text indisponível" in w for w in result["warnings"]))
        self.assertFalse(any("Nenhum termo da pergunta" in w for w in result["warnings"]))

    def test_semantic_only_results_are_flagged(self):
        result, _ = run([("T1", 0.6)], [])
        self.assertTrue(any("Nenhum termo da pergunta" in w for w in result["warnings"]))

    def test_question_without_terms_skips_fulltext(self):
        result, session = run([("T1", 0.6)], [("T2", 1.0)], question="o que é?")
        self.assertEqual(session.queries("fulltext.queryNodes"), [])
        self.assertTrue(any("não gerou termos" in w for w in result["warnings"]))


class InputValidationTests(unittest.TestCase):
    def test_empty_question_is_rejected(self):
        for question in ("", "   ", None, 42):
            with self.subTest(question=question), self.assertRaises(ValueError):
                run([], [], question=question)

    def test_invalid_top_k_is_rejected(self):
        for top_k in (0, -1, "5", True, 2.5):
            with self.subTest(top_k=top_k), self.assertRaises(ValueError):
                run([], [], top_k=top_k)

    def test_large_top_k_is_capped_with_warning(self):
        result, _ = run([("T1", 0.8)], [], top_k=MAX_TOP_K + 30)
        self.assertEqual(result["parameters"]["top_k"], MAX_TOP_K)
        self.assertTrue(any("reduzido" in w for w in result["warnings"]))

    def test_invalid_rrf_k_is_rejected(self):
        with self.assertRaises(ValueError):
            GraphHybridRetriever(FakeDriver(None), FakeEncoder(), rrf_k=0)


class FulltextQueryTests(unittest.TestCase):
    def test_stopwords_removed_and_or_semantics(self):
        query = build_fulltext_query("Quais empresas foram declaradas inidôneas para licitar?")
        self.assertEqual(query, "texto:(empresas OR declaradas OR inidôneas OR licitar)")

    def test_numbers_with_separators_generate_joined_and_phrase_forms(self):
        self.assertEqual(build_fulltext_query("Lei 12.846"), 'texto:(12846 OR "12.846" OR lei)')
        cnpj = build_fulltext_query("CNPJ 01.340.937/0001-79")
        self.assertIn("01340937000179", cnpj)
        self.assertIn('"01.340.937/0001-79"', cnpj)

    def test_lucene_operators_from_user_are_neutralized(self):
        query = build_fulltext_query('fraude AND (texto:*) OR "x" NOT y~ \\ ^2')
        inner = query[len("texto:("):-1]
        terms = inner.split(" OR ")
        for term in terms:
            self.assertRegex(term, r'^(\w+|"[\d./-]+")$')
        self.assertNotIn(" AND ", query)
        self.assertNotIn(" NOT ", query)

    def test_only_stopwords_yields_empty_query(self):
        self.assertEqual(build_fulltext_query("o que é a de?"), "")

    def test_terms_are_capped_and_deduplicated(self):
        query = build_fulltext_query(" ".join(f"termo{i} termo{i}" for i in range(40)), max_terms=5)
        self.assertEqual(query.count(" OR "), 4)


class SchemaAlignmentTests(unittest.TestCase):
    """Garante que os nomes usados no código são os do schema versionado."""

    def test_fulltext_index_exists_in_dev3_schema_and_covers_trecho_texto(self):
        schema = (ROOT / "cypher" / "01_schema_fiscalgraph.cypher").read_text(encoding="utf-8")
        match = re.search(
            rf"CREATE FULLTEXT INDEX {FULLTEXT_INDEX} IF NOT EXISTS\s+FOR \(n:([\w|]+)\)\s+ON EACH \[([^\]]+)\]",
            schema,
        )
        self.assertIsNotNone(match, "índice full-text não encontrado no schema de dev3")
        self.assertIn("Trecho", match.group(1).split("|"))
        self.assertIn("n.texto", match.group(2))

    def test_vector_index_file_matches_python_config(self):
        ddl = (ROOT / "cypher" / "04_indice_vetorial_trecho.cypher").read_text(encoding="utf-8")
        self.assertIn(f"CREATE VECTOR INDEX {embeddings.VECTOR_INDEX} IF NOT EXISTS", ddl)
        self.assertIn(f"`vector.dimensions`: {embeddings.EMBEDDING_DIMENSIONS}", ddl)
        self.assertIn(f"`vector.similarity_function`: '{embeddings.VECTOR_SIMILARITY}'", ddl)
        self.assertIn("FOR (t:Trecho) ON (t.embedding)", ddl)
        self.assertIn("FOR (t:Trecho) ON (t.embedding)", embeddings.CREATE_VECTOR_INDEX)

    def test_vector_index_problems(self):
        good = {"type": "VECTOR", "labelsOrTypes": ["Trecho"], "properties": ["embedding"],
                "options": {"indexConfig": {"vector.dimensions": 384, "vector.similarity_function": "COSINE"}}}
        self.assertEqual(embeddings.vector_index_problems(good), [])
        wrong_dim = dict(good, options={"indexConfig": {"vector.dimensions": 768,
                                                       "vector.similarity_function": "COSINE"}})
        self.assertTrue(any("768" in p for p in embeddings.vector_index_problems(wrong_dim)))
        self.assertTrue(embeddings.vector_index_problems(None))


def final_response_from(context):
    """Mapeamento da seção 7.2 de docs/recuperacao-hibrida.md: saída do dev5 → resposta do dev1.

    Usa só campos da resposta de retrieve_context, sem consulta extra ao banco. ``answer`` fica
    vazio porque é gerado pelo dev1.
    """
    chunks = context["chunks"]
    sources, seen = [], set()
    for chunk in chunks:
        source_id = chunk["registro_id"] or chunk["trecho_id"]
        if source_id not in seen:
            seen.add(source_id)
            sources.append({"id": source_id, "label": "Sancao" if chunk["registro_id"] else "Trecho",
                            "url": chunk["url_fonte"]})
    return {
        "answer": "",
        "cypher": context["cypher"],
        "sources": sources,
        "nodes": context["nodes"],
        "relationships": context["relationships"],
        "retrieval_relevance": (chunks[0]["rrf_score"] / context["parameters"]["rrf_max_score"]
                                if chunks else None),
        "abstained": not chunks,
        "warnings": list(context["warnings"]),
    }


class ContractCompatibilityTests(unittest.TestCase):
    """Compatibilidade com os consumidores: dev1 (resposta final) e dev6 (interface/grafo)."""

    def scenarios(self):
        return {
            "normal": run([("T2", 0.9), ("T1", 0.8)], [("T1", 3.0)])[0],
            "sem_evidencia": run([], [])[0],
            "so_fulltext": run(retrieval._Neo4jClientError("sem índice"), [("T1", 2.0)])[0],
            "so_vetorial": run([("T1", 0.6)], [])[0],
        }

    def test_service_output_passes_contract_validator_in_all_scenarios(self):
        for name, result in self.scenarios().items():
            with self.subTest(cenario=name):
                self.assertEqual(validate_retrieval_response(result), [])

    def test_dev6_graph_is_self_consistent(self):
        result = self.scenarios()["normal"]
        node_ids = [n["id"] for n in result["nodes"]]
        self.assertEqual(len(node_ids), len(set(node_ids)))
        for rel in result["relationships"]:
            self.assertIn(rel["source"], node_ids)
            self.assertIn(rel["target"], node_ids)
        for chunk in result["chunks"]:
            self.assertIn(f"Trecho:{chunk['trecho_id']}", node_ids)

    def test_dev1_final_response_can_be_built_from_retrieval_only(self):
        for name, context in self.scenarios().items():
            with self.subTest(cenario=name):
                final = final_response_from(context)
                self.assertEqual(set(final), {"answer", "cypher", "sources", "nodes", "relationships",
                                              "retrieval_relevance", "abstained", "warnings"})
                for source in final["sources"]:
                    self.assertIsInstance(source["id"], str)
                    self.assertIsInstance(source["label"], str)
                    self.assertTrue(source["url"] is None or isinstance(source["url"], str))
                if context["chunks"]:
                    self.assertFalse(final["abstained"])
                    self.assertGreater(final["retrieval_relevance"], 0)
                    self.assertLessEqual(final["retrieval_relevance"], 1)
                else:
                    self.assertTrue(final["abstained"])
                    self.assertIsNone(final["retrieval_relevance"])
                json.dumps(final, ensure_ascii=False)

    def test_rrf_max_score_matches_first_place_in_both_lists(self):
        result, _ = run([("T1", 0.9)], [("T1", 3.0)])
        self.assertAlmostEqual(result["chunks"][0]["rrf_score"], result["parameters"]["rrf_max_score"])

    def test_validator_detects_contract_violations(self):
        valid = self.scenarios()["normal"]
        cases = {
            "campo ausente": lambda r: r.pop("cypher"),
            "aresta para nó inexistente": lambda r: r["relationships"][0].update(target="Empresa:NAO-EXISTE"),
            "ordem errada": lambda r: r["chunks"].reverse(),
            "rank booleano": lambda r: r["chunks"][0].update(vector_rank=True),
            "chunk sem rank": lambda r: r["chunks"][0].update(vector_rank=None, fulltext_rank=None),
            "não serializável": lambda r: r["nodes"][0]["properties"].update(data=object()),
            "modo errado": lambda r: r.update(retrieval_mode="vector"),
            "sem evidência e sem aviso": lambda r: r.update(chunks=[], warnings=[]),
        }
        for name, mutate in cases.items():
            with self.subTest(caso=name):
                broken = copy.deepcopy(valid)
                mutate(broken)
                self.assertNotEqual(validate_retrieval_response(broken), [])


class SentenceEncoderTests(unittest.TestCase):
    class FakeTokenizer:
        def __call__(self, texts, add_special_tokens=True, verbose=True):
            assert verbose is False
            return {"input_ids": [[0] * (len(text.split()) + 2) for text in texts]}

    class FakeModel:
        max_seq_length = 128

        def __init__(self, dimension=384, value=0.1):
            self.dimension, self.value = dimension, value
            self.tokenizer = SentenceEncoderTests.FakeTokenizer()

        def get_sentence_embedding_dimension(self):
            return self.dimension

        def encode(self, texts, **kwargs):
            assert kwargs["normalize_embeddings"] is True
            return [[self.value] * self.dimension for _ in texts]

    def test_rejects_model_with_other_dimension(self):
        with self.assertRaises(RuntimeError):
            embeddings.SentenceEncoder(model=self.FakeModel(dimension=768))

    def test_encode_returns_python_floats_with_384_dimensions(self):
        vectors = embeddings.SentenceEncoder(model=self.FakeModel()).encode(["a", "b"])
        self.assertEqual([len(v) for v in vectors], [384, 384])
        self.assertIsInstance(vectors[0][0], float)

    def test_encode_rejects_non_finite_values(self):
        with self.assertRaises(ValueError):
            embeddings.SentenceEncoder(model=self.FakeModel(value=float("nan"))).encode(["a"])

    def test_count_tokens_includes_special_tokens(self):
        encoder = embeddings.SentenceEncoder(model=self.FakeModel())
        self.assertEqual(encoder.count_tokens(["um dois", "um"]), [4, 3])


class TruncationSummaryTests(unittest.TestCase):
    def test_counts_texts_above_model_limit(self):
        summary = embeddings.truncation_summary([27, 130, 128, 720, 209], limit=128)
        self.assertEqual(summary["acima_do_limite"], 3)  # 130, 209 e 720; 128 cabe
        self.assertEqual((summary["total"], summary["minimo"], summary["maximo"]), (5, 27, 720))
        self.assertEqual(summary["mediana"], 130)

    def test_empty_input(self):
        summary = embeddings.truncation_summary([], limit=128)
        self.assertEqual((summary["total"], summary["acima_do_limite"], summary["mediana"]), (0, 0, None))


def load_audit_script():
    spec = importlib.util.spec_from_file_location(
        "audit_embedding_truncation", ROOT / "scripts" / "audit_embedding_truncation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TruncationAuditTests(unittest.TestCase):
    """scripts/audit_embedding_truncation.py, com tokenizador falso (1 token por palavra)."""

    @classmethod
    def setUpClass(cls):
        cls.audit = load_audit_script()

    @staticmethod
    def words(text):
        return len(text.split())

    def test_field_report_separates_legal_text_contribution(self):
        records = [
            {"descricao": "a b", "observacoes": "", "fundamentacao_legal": "x " * 10},
            {"descricao": "a", "observacoes": "c d", "fundamentacao_legal": "y"},
        ]
        # limite 8 com 2 especiais: passa do limite quem tem mais de 6 palavras.
        report = self.audit.field_report(records, self.words, limit=8, special_tokens=2)
        self.assertEqual(report["acima_com_texto_completo"], 1)
        self.assertEqual(report["acima_sem_fundamentacao_legal"], 0)
        self.assertEqual(report["fundamentacao_legal_sozinha_acima"], 1)
        self.assertEqual(report["campos"]["descricao"]["mediana"], 1.5)
        self.assertEqual(report["campos"]["observacoes"]["vazios"], 1)
        self.assertEqual(report["campos"]["fundamentacao_legal"]["maximo"], 10)

    def test_embedded_text_follows_dev4_composition(self):
        from pipeline.text_to_graph.extractor import CPF_MASK

        record = {"descricao": " Multa ", "observacoes": "", "fundamentacao_legal": "CPF 123.456.789-00"}
        text = self.audit.embedded_text(record)
        self.assertTrue(text.startswith("Multa"))
        self.assertIn(CPF_MASK, text)
        self.assertNotIn("123.456.789-00", text)


if __name__ == "__main__":
    unittest.main()
