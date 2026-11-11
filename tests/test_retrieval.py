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

from app.services import embeddings, multi_hop, retrieval  # noqa: E402
from app.services.contract import (  # noqa: E402
    example_final_response,
    validate_company_paths_response,
    validate_retrieval_response,
)
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
R_MENCIONA = rel("r:me", "MENCIONA", T1, EST, status="CANDIDATA", inicio=10, fim=28,
                 metodo="regex_cnpj_estrutural")
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
    def __init__(self, vector, fulltext, expansion=EXPANSION, embedding_status=(2, 2)):
        self.vector, self.fulltext, self.expansion = vector, fulltext, expansion
        self.embedding_status = embedding_status  # (com_embedding, na_versao_atual)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, parameters=None, **kwargs):
        params = dict(parameters or {}, **kwargs)
        self.calls.append((query, params))
        if "na_versao_atual" in query:
            total, current = self.embedding_status
            return [{"com_embedding": total, "na_versao_atual": current}]
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

    def test_active_searches_identify_effective_mode(self):
        expected = {
            "normal": (["vector", "fulltext"], {"vector": "com_resultados", "fulltext": "com_resultados"}),
            "sem_evidencia": ([], {"vector": "sem_resultados", "fulltext": "sem_resultados"}),
            "so_fulltext": (["fulltext"], {"vector": "indisponivel", "fulltext": "com_resultados"}),
            "so_vetorial": (["vector"], {"vector": "com_resultados", "fulltext": "sem_resultados"}),
        }
        for name, result in self.scenarios().items():
            with self.subTest(cenario=name):
                self.assertEqual(result["retrieval_mode"], "hybrid")  # campo do contrato preservado
                parameters = result["parameters"]
                self.assertEqual((parameters["active_searches"], parameters["search_status"]), expected[name])

    def test_question_without_terms_marks_fulltext_as_not_executed(self):
        result, _ = run([("T1", 0.6)], [("T2", 1.0)], question="o que é?")
        self.assertEqual(result["parameters"]["search_status"]["fulltext"], "nao_executada")
        self.assertEqual(result["parameters"]["active_searches"], ["vector"])

    def test_dev6_graph_is_self_consistent(self):
        result = self.scenarios()["normal"]
        node_ids = [n["id"] for n in result["nodes"]]
        self.assertEqual(len(node_ids), len(set(node_ids)))
        for rel_item in result["relationships"]:
            self.assertIn(rel_item["source"], node_ids)
            self.assertIn(rel_item["target"], node_ids)
        for chunk in result["chunks"]:
            self.assertIn(f"Trecho:{chunk['trecho_id']}", node_ids)

    def test_dev6_fields_have_expected_formats(self):
        result = self.scenarios()["normal"]
        for chunk in result["chunks"]:
            self.assertTrue(all(isinstance(p, str) for p in chunk["graph_paths"]))
            for key in ("vector_score", "fulltext_score"):
                self.assertTrue(chunk[key] is None or isinstance(chunk[key], float))
        mention = next(r for r in result["relationships"] if r["type"] == "MENCIONA")
        self.assertEqual(mention["properties"],
                         {"status": "CANDIDATA", "inicio": 10, "fim": 28, "metodo": "regex_cnpj_estrutural"})
        self.assertEqual(json.loads(json.dumps(result, ensure_ascii=False)), result)

    def test_dev1_final_response_can_be_built_from_retrieval_only(self):
        for name, context in self.scenarios().items():
            with self.subTest(cenario=name):
                final = example_final_response(context)
                self.assertEqual(set(final), {"answer", "cypher", "sources", "nodes", "relationships",
                                              "retrieval_relevance", "abstained", "warnings"})
                expected_sources, seen_ids = [], set()
                for chunk in context["chunks"]:
                    source_id = chunk["registro_id"] or chunk["trecho_id"]
                    if source_id not in seen_ids:
                        seen_ids.add(source_id)
                        expected_sources.append({
                            "id": source_id,
                            "label": "Sancao" if chunk["registro_id"] else "Trecho",
                            "url": chunk["url_fonte"],
                        })
                self.assertEqual(final["sources"], expected_sources)
                for source in final["sources"]:
                    self.assertEqual(set(source), {"id", "label", "url"})
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

    def test_final_response_deduplicates_sources_by_record_id(self):
        context = copy.deepcopy(self.scenarios()["normal"])
        duplicate = copy.deepcopy(context["chunks"][0])
        duplicate["trecho_id"] = "TRECHO-DUPLICADO-MESMO-REGISTRO"
        context["chunks"].append(duplicate)

        final = example_final_response(context)
        ids = [source["id"] for source in final["sources"]]
        self.assertEqual(ids.count(context["chunks"][0]["registro_id"]), 1)

    def test_rrf_max_score_matches_first_place_in_both_lists(self):
        result, _ = run([("T1", 0.9)], [("T1", 3.0)])
        self.assertAlmostEqual(result["chunks"][0]["rrf_score"], result["parameters"]["rrf_max_score"])

    def test_validator_detects_contract_violations(self):
        valid = self.scenarios()["normal"]
        mention = next(i for i, r in enumerate(valid["relationships"]) if r["type"] == "MENCIONA")
        cases = {
            "campo ausente": lambda r: r.pop("cypher"),
            "parameters ausente": lambda r: r.pop("parameters"),
            "aresta para nó inexistente": lambda r: r["relationships"][0].update(target="Empresa:NAO-EXISTE"),
            "ordem errada": lambda r: r["chunks"].reverse(),
            "rank booleano": lambda r: r["chunks"][0].update(vector_rank=True),
            "chunk sem rank": lambda r: r["chunks"][0].update(vector_rank=None, fulltext_rank=None),
            "score sem rank": lambda r: r["chunks"][1].update(fulltext_score=1.0),
            "score não finito": lambda r: r["chunks"][0].update(vector_score=float("nan")),
            "rrf incoerente com os ranks": lambda r: r["chunks"][0].update(rrf_score=0.02),
            "graph_paths não é lista de textos": lambda r: r["chunks"][0].update(graph_paths="(Trecho:T1)"),
            "embedding exposto no nó": lambda r: r["nodes"][0]["properties"].update(embedding=[0.1]),
            "texto duplicado no nó": lambda r: r["nodes"][0]["properties"].update(texto="..."),
            "MENCIONA sem status": lambda r: r["relationships"][mention]["properties"].pop("status"),
            "active_searches incoerente": lambda r: r["parameters"].update(active_searches=["vector"]),
            "busca desconhecida": lambda r: r["parameters"].update(active_searches=["sql"]),
            "identifier_matches ausente": lambda r: r["chunks"][0].pop("identifier_matches"),
            "identificador fora da pergunta": lambda r: r["chunks"][0].update(identifier_matches=["99999999000199"]),
            "não serializável": lambda r: r["nodes"][0]["properties"].update(data=object()),
            "modo errado": lambda r: r.update(retrieval_mode="vector"),
            "sem evidência e sem aviso": lambda r: r.update(chunks=[], warnings=[]),
        }
        for name, mutate in cases.items():
            with self.subTest(caso=name):
                broken = copy.deepcopy(valid)
                mutate(broken)
                self.assertNotEqual(validate_retrieval_response(broken), [])


class IdentifierMatchTests(unittest.TestCase):
    """CNPJ na pergunta: a correspondência literal é sinalizada sem reordenar o RRF."""

    def run_with_cnpj_in(self, holder, question="trecho que cita o CNPJ 11.222.333/0001-81"):
        expansion = copy.deepcopy(EXPANSION)
        expansion[holder]["texto"] = "Multa aplicada à empresa de CNPJ nº 11.222.333/0001-81."
        session = FakeSession([("T1", 0.9), ("T2", 0.8)], [("T1", 2.0), ("T2", 1.5)], expansion=expansion)
        return GraphHybridRetriever(FakeDriver(session), FakeEncoder()).retrieve_context(question)

    def test_literal_match_is_flagged_and_warned_when_not_first(self):
        result = self.run_with_cnpj_in("T2")
        self.assertEqual(result["parameters"]["query_identifiers"], ["11222333000181"])
        self.assertEqual([c["trecho_id"] for c in result["chunks"]], ["T1", "T2"])  # ordem do RRF mantida
        self.assertEqual([c["identifier_matches"] for c in result["chunks"]], [[], ["11222333000181"]])
        warning = next(w for w in result["warnings"] if w.startswith("A pergunta cita CNPJ"))
        self.assertIn("2º trecho (T2, registro SINT-CEIS-2)", warning)
        self.assertEqual(validate_retrieval_response(result), [])

    def test_no_warning_when_first_chunk_contains_the_cnpj(self):
        result = self.run_with_cnpj_in("T1")
        self.assertEqual(result["chunks"][0]["identifier_matches"], ["11222333000181"])
        self.assertFalse(any(w.startswith("A pergunta cita CNPJ") for w in result["warnings"]))

    def test_questions_without_cnpj_have_empty_matches(self):
        result, _ = run([("T1", 0.8)], [("T1", 2.0)])
        self.assertEqual(result["parameters"]["query_identifiers"], [])
        self.assertEqual(result["chunks"][0]["identifier_matches"], [])

    def test_identifier_extraction_follows_dev4_rules(self):
        self.assertEqual(retrieval.cnpj_identifiers("CNPJ 01.340.937/0001-79 e 00478727000189"),
                         ["01340937000179", "00478727000189"])
        self.assertEqual(retrieval.cnpj_identifiers("Lei 12.846 de 2013"), [])


class EmbeddingVersionWarningTests(unittest.TestCase):
    def test_outdated_stored_embeddings_are_reported(self):
        session = FakeSession([("T1", 0.8)], [("T1", 2.0)], embedding_status=(54, 10))
        retriever = GraphHybridRetriever(FakeDriver(session), FakeEncoder())
        result = retriever.retrieve_context("sanção sintética")
        self.assertTrue(any("44 de 54 Trecho têm embedding de outro modelo" in w for w in result["warnings"]))
        self.assertEqual(result["parameters"]["embedding_pipeline_version"], embeddings.EMBEDDING_PIPELINE_VERSION)

    def test_current_embeddings_do_not_warn_and_are_checked_once(self):
        session = FakeSession([("T1", 0.8)], [("T1", 2.0)], embedding_status=(54, 54))
        retriever = GraphHybridRetriever(FakeDriver(session), FakeEncoder())
        for _ in range(2):
            result = retriever.retrieve_context("sanção sintética")
            self.assertFalse(any("outra versão" in w for w in result["warnings"]))
        self.assertEqual(len(session.queries("na_versao_atual")), 1)


# --------------------------------------------------------------------------- embeddings
class FakeTokenizer:
    """1 token por palavra, ids estáveis por palavra; especiais 0 (início) e 2 (fim)."""

    pad_token_id = 1

    def __init__(self):
        self.vocab = {}

    def __call__(self, text, add_special_tokens=True, verbose=True):
        assert verbose is False
        ids = [self.vocab.setdefault(word, len(self.vocab) + 10) for word in text.split()]
        return {"input_ids": [0] + ids + [2] if add_special_tokens else ids}


class FakeModel:
    max_seq_length = 128

    def __init__(self, dimension=384):
        self.dimension = dimension
        self.tokenizer = FakeTokenizer()

    def get_sentence_embedding_dimension(self):
        return self.dimension


class RecordingEncoder(embeddings.SentenceEncoder):
    """Troca só a chamada ao modelo por um vetor determinístico; registra as janelas recebidas."""

    def __init__(self, value=None, **kwargs):
        super().__init__(model=FakeModel(), **kwargs)
        self.windows_seen = []
        self.value = value

    def _forward_ids(self, windows):
        vectors = []
        for ids in windows:
            self.windows_seen.append(list(ids))
            vector = [0.0] * embeddings.EMBEDDING_DIMENSIONS
            for token in ids:
                vector[token % embeddings.EMBEDDING_DIMENSIONS] += 1.0
            vector[-1] += 0.5  # janela vazia também gera vetor não nulo
            if self.value is not None:
                vector[0] = self.value
            vectors.append(vector)
        return vectors


def words(n, prefix="p"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def norm(vector):
    return sum(v * v for v in vector) ** 0.5


class TokenWindowTests(unittest.TestCase):
    def test_short_text_is_a_single_window(self):
        self.assertEqual(embeddings.token_windows(10, 126, 32), [(0, 10)])
        self.assertEqual(embeddings.token_windows(126, 126, 32), [(0, 126)])
        self.assertEqual(embeddings.token_windows(0, 126, 32), [(0, 0)])

    def test_long_text_windows_overlap_and_end_at_last_token(self):
        spans = embeddings.token_windows(718, 126, 32)
        self.assertEqual(spans[0], (0, 126))
        self.assertEqual(spans[-1], (592, 718))
        self.assertEqual(len(spans), 8)
        for (_, e1), (s2, e2) in zip(spans, spans[1:]):
            self.assertLessEqual(e2 - s2, 126)
            self.assertGreaterEqual(e1 - s2, 32)  # sobreposição mínima entre vizinhas
        self.assertEqual(embeddings.uncovered_tokens(718, spans), 0)

    def test_every_length_is_fully_covered(self):
        for n in range(0, 800, 7):
            with self.subTest(n=n):
                spans = embeddings.token_windows(n, 126, 32)
                self.assertEqual(embeddings.uncovered_tokens(n, spans), 0)
                self.assertTrue(all(end - start <= 126 for start, end in spans))
                self.assertEqual(sum(embeddings.new_token_weights(spans)), max(n, 1))

    def test_invalid_window_parameters(self):
        for size, overlap in ((0, 0), (126, 126), (126, -1)):
            with self.subTest(size=size, overlap=overlap), self.assertRaises(ValueError):
                embeddings.token_windows(200, size, overlap)

    def test_uncovered_tokens_detects_gaps(self):
        self.assertEqual(embeddings.uncovered_tokens(10, [(0, 4), (6, 10)]), 2)


class AggregationTests(unittest.TestCase):
    def unit(self, index):
        vector = [0.0] * embeddings.EMBEDDING_DIMENSIONS
        vector[index] = 1.0
        return vector

    def test_weighted_mean_then_l2_normalization(self):
        result = embeddings.aggregate_window_vectors([self.unit(0), self.unit(1)], [3, 1])
        self.assertAlmostEqual(result[0], 3 / 10 ** 0.5)
        self.assertAlmostEqual(result[1], 1 / 10 ** 0.5)
        self.assertAlmostEqual(norm(result), 1.0)

    def test_window_vectors_are_normalized_before_averaging(self):
        big = [v * 100 for v in self.unit(0)]
        result = embeddings.aggregate_window_vectors([big, self.unit(1)], [1, 1])
        self.assertAlmostEqual(result[0], result[1])

    def test_rejects_invalid_inputs(self):
        nan = self.unit(0)
        nan[5] = float("nan")
        inf = self.unit(0)
        inf[5] = float("inf")
        cases = {
            "NaN": ([nan], [1]), "infinito": ([inf], [1]), "dimensão errada": ([[1.0] * 10], [1]),
            "vetor nulo": ([[0.0] * 384], [1]), "peso zero": ([self.unit(0)], [0]),
            "pesos e vetores desalinhados": ([self.unit(0)], [1, 1]), "sem vetores": ([], []),
        }
        for name, (vectors, weights) in cases.items():
            with self.subTest(caso=name), self.assertRaises(ValueError):
                embeddings.aggregate_window_vectors(vectors, weights)


class SentenceEncoderTests(unittest.TestCase):
    def test_rejects_model_with_other_dimension(self):
        with self.assertRaises(RuntimeError):
            embeddings.SentenceEncoder(model=FakeModel(dimension=768))

    def test_special_tokens_and_effective_limit(self):
        encoder = RecordingEncoder()
        self.assertEqual((encoder.prefix, encoder.suffix, encoder.special_tokens), ([0], [2], 2))
        self.assertEqual((encoder.default_max_seq_length, encoder.max_seq_length), (128, 128))
        self.assertEqual(encoder.model.max_seq_length, 128)

    def test_window_must_fit_architecture_positions(self):
        with self.assertRaises(ValueError):
            RecordingEncoder(window_tokens=511)  # 511 + 2 especiais > 512 posições

    def test_short_text_uses_one_window_like_a_direct_embedding(self):
        encoder = RecordingEncoder()
        text = words(10)
        vector = encoder.encode([text])[0]
        ids = encoder.content_token_ids(text)
        self.assertEqual(encoder.windows_seen, [ids])
        direct = embeddings.l2_normalize(encoder._forward_ids([ids])[0])
        for got, want in zip(vector, direct):
            self.assertAlmostEqual(got, want, places=12)

    def test_text_above_512_tokens_is_segmented_by_tokenizer_windows(self):
        encoder = RecordingEncoder()
        text = words(600)
        encoder.encode([text])
        ids = encoder.content_token_ids(text)
        expected = [ids[s:e] for s, e in embeddings.token_windows(600, 126, 32)]
        self.assertEqual(encoder.windows_seen, expected)
        self.assertTrue(all(len(w) <= 126 for w in encoder.windows_seen))
        self.assertGreater(len(encoder.windows_seen), 1)

    def test_final_content_is_represented(self):
        encoder = RecordingEncoder()
        text = words(600)
        encoder.encode([text])
        last_token = encoder.content_token_ids(text)[-1]
        self.assertIn(last_token, encoder.windows_seen[-1])
        plan = encoder.window_plan(text)
        self.assertEqual((plan["tokens"], plan["tokens_nao_representados"]), (600, 0))

    def test_multiple_windows_are_aggregated_with_new_token_weights(self):
        encoder = RecordingEncoder()
        text = words(300)
        vector = encoder.encode([text])[0]
        spans = embeddings.token_windows(300, 126, 32)
        ids = encoder.content_token_ids(text)
        window_vectors = encoder._forward_ids([ids[s:e] for s, e in spans])
        expected = embeddings.aggregate_window_vectors(window_vectors, embeddings.new_token_weights(spans))
        self.assertEqual(vector, expected)

    def test_output_has_384_finite_dimensions_and_unit_norm(self):
        for vector in RecordingEncoder().encode([words(5), words(700), ""]):
            self.assertEqual(len(vector), 384)
            self.assertTrue(all(isinstance(v, float) and v == v for v in vector))
            self.assertAlmostEqual(norm(vector), 1.0)

    def test_non_finite_model_output_is_rejected(self):
        for value in (float("nan"), float("inf")):
            with self.subTest(valor=value), self.assertRaises(ValueError):
                RecordingEncoder(value=value).encode([words(3)])

    def test_documents_and_questions_share_the_same_encoding(self):
        encoder = RecordingEncoder()
        question = "empresas declaradas inidôneas"
        alone = encoder.encode([question])[0]
        in_document_batch = encoder.encode([words(400), question, words(20)])[1]
        self.assertEqual(alone, in_document_batch)

    def test_count_tokens_includes_special_tokens(self):
        self.assertEqual(RecordingEncoder().count_tokens(["um dois", "um"]), [4, 3])

    def test_pipeline_version_tracks_the_strategy(self):
        self.assertEqual(embeddings.pipeline_version(), embeddings.EMBEDDING_PIPELINE_VERSION)
        self.assertEqual(RecordingEncoder().pipeline_version, embeddings.EMBEDDING_PIPELINE_VERSION)
        self.assertNotEqual(embeddings.pipeline_version(254, 64), embeddings.EMBEDDING_PIPELINE_VERSION)
        self.assertNotEqual(embeddings.pipeline_version(126, 16), embeddings.EMBEDDING_PIPELINE_VERSION)
        self.assertTrue(embeddings.EMBEDDING_PIPELINE_VERSION.startswith("v2-"))


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GeneratorVerificationTests(unittest.TestCase):
    """Regras do gerador que não dependem do banco; a consulta de pendentes é testada na integração."""

    @classmethod
    def setUpClass(cls):
        cls.generator = load_script("generate_embeddings")

    def check(self, **changes):
        base = {"total": 54, "com_embedding": 54, "dimensao_min": 384, "dimensao_max": 384,
                "norma_min": 0.9999999, "norma_max": 1.0000001, "na_versao_atual": 54}
        base.update(changes)
        return self.generator.verification_problems(base, complete_run=True)

    def test_consistent_state_has_no_problems(self):
        self.assertEqual(self.check(), [])

    def test_detects_old_version_wrong_dimension_and_unnormalized_vectors(self):
        self.assertTrue(any("versão atual" in p for p in self.check(na_versao_atual=40)))
        self.assertTrue(any("dimensões" in p for p in self.check(dimensao_min=128)))
        self.assertTrue(any("normalizados" in p for p in self.check(norma_max=1.2)))

    def test_pending_query_reprocesses_old_strategy_versions(self):
        query = self.generator.SELECT_PENDING
        self.assertIn("t.embedding_pipeline_version IS NULL OR t.embedding_pipeline_version <> $version", query)
        self.assertIn("'versao_antiga'", query)
        self.assertIn("t.embedding_pipeline_version = $version", self.generator.WRITE_EMBEDDINGS.replace(
            "t.embedding_pipeline_version = $version,", "t.embedding_pipeline_version = $version"))


# --------------------------------------------------------------------------- company_paths
EMP_A = node("p:ea", ["Empresa"], cnpj_basico="A0000001", razao_social="EMPRESA SINTETICA A")
EMP_B = node("p:eb", ["Empresa"], cnpj_basico="B0000002", razao_social="EMPRESA SINTETICA B")
EST_A = node("p:sa", ["Estabelecimento"], cnpj="A0000001000100", cnpj_basico="A0000001")
EST_B = node("p:sb", ["Estabelecimento"], cnpj="B0000002000100", cnpj_basico="B0000002")
CNAE_X = node("p:c", ["CNAE"], codigo="0000000", descricao="Atividade sintética")
SOCIO_X = node("p:s", ["Socio"], socio_id="SOC-X", tipo_pessoa="PESSOA FISICA", nome="NAO DEVE SAIR")
CNAE_PATH = {"nodes": [EMP_A, EST_A, CNAE_X, EST_B, EMP_B], "relationships": [
    rel("p:r1", "POSSUI_ESTABELECIMENTO", EMP_A, EST_A), rel("p:r2", "EXERCE_CNAE", EST_A, CNAE_X),
    rel("p:r3", "EXERCE_CNAE", EST_B, CNAE_X), rel("p:r4", "POSSUI_ESTABELECIMENTO", EMP_B, EST_B)]}
SOCIO_PATH = {"nodes": [EMP_A, SOCIO_X, EMP_B], "relationships": [
    rel("p:q1", "PARTICIPA_DE", SOCIO_X, EMP_A), rel("p:q2", "PARTICIPA_DE", SOCIO_X, EMP_B)]}


class FakePathSession:
    def __init__(self, existing=("A0000001", "B0000002"), societario=None, estrutural=None):
        self.existing, self.societario, self.estrutural = existing, societario, estrutural
        self.queries = []

    def run(self, query, parameters=None):
        self.queries.append(query)
        if "UNWIND $ids" in query:
            return [{"id": i, "existe": i in self.existing} for i in parameters["ids"]]
        found = self.estrutural if "EXERCE_CNAE" in query else self.societario
        return [found] if found else []


class CompanyPathsTests(unittest.TestCase):
    def paths(self, **kwargs):
        return multi_hop.find_company_paths(FakePathSession(**kwargs), "A0000001", "B0000002")

    def test_cnae_path_is_classified_and_explained(self):
        result = self.paths(estrutural=CNAE_PATH)
        self.assertEqual(validate_company_paths_response(result), [])
        (found,) = result["paths"]
        self.assertEqual((found["kind"], found["length"]), ("atividade_cnae", 4))
        self.assertEqual(found["nodes"], ["Empresa:A0000001", "Estabelecimento:A0000001000100", "CNAE:0000000",
                                          "Estabelecimento:B0000002000100", "Empresa:B0000002"])
        self.assertIn("-[:EXERCE_CNAE]->(CNAE:0000000)<-[:EXERCE_CNAE]-", found["text"])
        self.assertIn(multi_hop.CNAE_WARNING, result["warnings"])
        self.assertTrue(any("Nenhum caminho societário" in w for w in result["warnings"]))

    def test_societal_path_is_reported_once_and_minimizes_personal_data(self):
        result = self.paths(societario=SOCIO_PATH, estrutural=SOCIO_PATH)
        self.assertEqual(validate_company_paths_response(result), [])
        self.assertEqual([p["kind"] for p in result["paths"]], ["societario"])
        socio = next(n for n in result["nodes"] if n["label"] == "Socio")
        self.assertNotIn("nome", socio["properties"])
        self.assertFalse(any("Nenhum caminho societário" in w for w in result["warnings"]))

    def test_missing_company_returns_warning_without_paths(self):
        result = self.paths(existing=("A0000001",))
        self.assertEqual((result["paths"], result["nodes"]), ([], []))
        self.assertTrue(any("B0000002" in w for w in result["warnings"]))
        self.assertEqual(validate_company_paths_response(result), [])

    def test_no_path_is_reported(self):
        result = self.paths()
        self.assertTrue(any("Nenhum caminho com até 6" in w for w in result["warnings"]))

    def test_mention_path_is_marked_as_candidate(self):
        mention = {"nodes": [EMP_A, EST_A, EMP_B], "relationships": [
            rel("p:m1", "POSSUI_ESTABELECIMENTO", EMP_A, EST_A), rel("p:m2", "MENCIONA", EST_A, EMP_B)]}
        self.assertEqual(multi_hop.classify_path(mention), "mencao_candidata")

    def test_queries_are_limited_and_skip_provenance(self):
        session = FakePathSession(estrutural=CNAE_PATH)
        multi_hop.find_company_paths(session, "A0000001", "B0000002", max_hops=4)
        path_queries = [q for q in session.queries if "shortestPath" in q]
        self.assertEqual(len(path_queries), 2)
        self.assertTrue(all("*..4]" in q and "ORIGINADO_DE" not in q for q in path_queries))

    def test_invalid_inputs_are_rejected(self):
        for args in (("A0000001", "A0000001", 6), ("", "B0000002", 6), ("A0000001", "B0000002", 0),
                     ("A0000001", "B0000002", 7), ("A0000001", "B0000002", True), (None, "B0000002", 6)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                multi_hop.find_company_paths(FakePathSession(), *args)

    def test_validator_detects_broken_paths(self):
        valid = self.paths(estrutural=CNAE_PATH)
        cases = {
            "tipo de caminho inválido": lambda r: r["paths"][0].update(kind="vinculo"),
            "nó do caminho ausente": lambda r: r["paths"][0]["nodes"].append("Empresa:X"),
            "length incoerente": lambda r: r["paths"][0].update(length=2),
            "aresta solta": lambda r: r["relationships"][0].update(source="Empresa:X"),
        }
        for name, mutate in cases.items():
            with self.subTest(caso=name):
                broken = copy.deepcopy(valid)
                mutate(broken)
                self.assertNotEqual(validate_company_paths_response(broken), [])


class TruncationSummaryTests(unittest.TestCase):
    def test_counts_texts_above_model_limit(self):
        summary = embeddings.truncation_summary([27, 130, 128, 720, 209], limit=128)
        self.assertEqual(summary["acima_do_limite"], 3)  # 130, 209 e 720; 128 cabe
        self.assertEqual((summary["total"], summary["minimo"], summary["maximo"]), (5, 27, 720))
        self.assertEqual(summary["mediana"], 130)

    def test_empty_input(self):
        summary = embeddings.truncation_summary([], limit=128)
        self.assertEqual((summary["total"], summary["acima_do_limite"], summary["mediana"]), (0, 0, None))


class TruncationAuditTests(unittest.TestCase):
    """scripts/audit_embedding_truncation.py, com tokenizador falso (1 token por palavra)."""

    @classmethod
    def setUpClass(cls):
        cls.audit = load_script("audit_embedding_truncation")

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
