"""Integração do retrieve_context com o Neo4j real e o modelo de embeddings (dev5).

Valida o contrato (app/services/contract.py) sobre respostas reais e a procedência dos trechos.
Exige Neo4j ativo com a carga de dev3 + dev4, embeddings gerados (scripts/generate_embeddings.py),
NEO4J_PASSWORD (variável de ambiente ou .env) e sentence-transformers instalado. Sem isso, é
ignorado (skip). Só lê o banco.

Executar na raiz do repositório:
    python -m unittest discover -s tests -p "test_retrieval_integracao.py" -v
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.contract import (  # noqa: E402
    validate_company_paths_response,
    validate_retrieval_response,
)
from app.services.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_PIPELINE_VERSION, MODEL_NAME  # noqa: E402

QUESTIONS = (
    "Quais empresas foram declaradas inidôneas para licitar com a administração pública?",
    "empresa impedida de fechar contratos com o governo",
    "Lei 12.846 publicação extraordinária da decisão condenatória",
    "trecho que cita o CNPJ 01.340.937/0001-79",
)
OUT_OF_SCOPE = "receita de bolo de chocolate"


class RetrieveContextIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec("sentence_transformers") is None:
            raise unittest.SkipTest("sentence-transformers não instalado (requirements-dev5.txt).")
        try:
            from dotenv import load_dotenv
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise unittest.SkipTest(f"dependência ausente: {exc}")
        load_dotenv(ROOT / ".env")
        password = os.getenv("NEO4J_PASSWORD")
        if not password or password == "change_this_password_before_starting":
            raise unittest.SkipTest("NEO4J_PASSWORD não configurado; teste de integração ignorado.")
        cls.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), password),
        )
        try:
            cls.driver.verify_connectivity()
            with cls.driver.session() as session:
                row = session.run(
                    "MATCH (t:Trecho) RETURN count(t) AS total, "
                    "count(CASE WHEN size(t.embedding) = $dim THEN 1 END) AS com_embedding",
                    dim=EMBEDDING_DIMENSIONS,
                ).single()
        except Exception as exc:  # banco desligado ou credencial errada
            cls.driver.close()
            raise unittest.SkipTest(f"Neo4j inacessível: {exc}")
        if row["total"] == 0 or row["com_embedding"] != row["total"]:
            cls.driver.close()
            raise unittest.SkipTest(
                f"{row['com_embedding']}/{row['total']} Trecho com embedding; rode scripts/generate_embeddings.py."
            )
        from app.services.retrieval import GraphHybridRetriever

        cls.retriever = GraphHybridRetriever(cls.driver, database=os.getenv("NEO4J_DATABASE") or None)
        cls.results = {q: cls.retriever.retrieve_context(q, top_k=5) for q in QUESTIONS + (OUT_OF_SCOPE,)}

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()

    def test_real_responses_satisfy_contract(self):
        for question, result in self.results.items():
            with self.subTest(pergunta=question):
                self.assertEqual(validate_retrieval_response(result), [])
                self.assertEqual(len(result["chunks"]), 5)

    def test_real_chunks_keep_provenance_and_graph_path(self):
        for question in QUESTIONS:
            for chunk in self.results[question]["chunks"]:
                with self.subTest(pergunta=question, trecho=chunk["trecho_id"]):
                    self.assertIsNotNone(chunk["registro_id"])
                    self.assertIsNotNone(chunk["fonte_id"])
                    self.assertTrue(chunk["url_fonte"].startswith("https://"))
                    self.assertTrue(any("-[:EXTRATO_DE]->(Sancao:" in p for p in chunk["graph_paths"]))
                    self.assertTrue(any("-[:ORIGINADO_DE]->(Fonte:" in p for p in chunk["graph_paths"]))

    def test_both_searches_contribute(self):
        for question in QUESTIONS:
            chunks = self.results[question]["chunks"]
            with self.subTest(pergunta=question):
                self.assertTrue(any(c["vector_rank"] for c in chunks))
                self.assertTrue(any(c["fulltext_rank"] for c in chunks))

    def test_formatted_cnpj_is_found_by_fulltext_and_flagged(self):
        """O trecho com o CNPJ literal é o 1º do full-text e vem marcado em identifier_matches.

        Até a estratégia v1 ele também era o 1º do RRF; com o vetor do texto inteiro, outro trecho que
        cita um CNPJ diferente ficou 1º na busca vetorial e passou à frente por consenso (seção 10.3 de
        docs/recuperacao-hibrida.md). O serviço então avisa onde está a correspondência literal.
        """
        result = self.results["trecho que cita o CNPJ 01.340.937/0001-79"]
        self.assertEqual(result["parameters"]["query_identifiers"], ["01340937000179"])
        exact = [c for c in result["chunks"] if c["identifier_matches"] == ["01340937000179"]]
        self.assertEqual([(c["registro_id"], c["fulltext_rank"]) for c in exact], [("CEIS-289814", 1)])
        position = result["chunks"].index(exact[0]) + 1
        self.assertLessEqual(position, 2)
        if position > 1:
            self.assertTrue(any("2º trecho" in w and "CEIS-289814" in w for w in result["warnings"]))

    def test_out_of_scope_question_is_flagged(self):
        result = self.results[OUT_OF_SCOPE]
        self.assertTrue(all(c["fulltext_rank"] is None for c in result["chunks"]))
        self.assertTrue(any("Nenhum termo da pergunta" in w for w in result["warnings"]))

    def test_active_searches_reflect_what_contributed(self):
        for question in QUESTIONS:
            with self.subTest(pergunta=question):
                self.assertEqual(self.results[question]["parameters"]["active_searches"], ["vector", "fulltext"])
        out = self.results[OUT_OF_SCOPE]["parameters"]
        self.assertEqual((out["active_searches"], out["search_status"]["fulltext"]), (["vector"], "sem_resultados"))

    def test_question_and_document_encoding_match_the_model(self):
        """Texto de uma janela: o vetor do SentenceEncoder é o mesmo do SentenceTransformer.encode."""
        encoder = self.retriever.encoder
        texts = ["Quais empresas foram declaradas inidôneas?", "Multa aplicada com base na Lei 12.846"]
        ours = encoder.encode(texts)
        reference = encoder.model.encode(texts, normalize_embeddings=True).tolist()
        for got, want in zip(ours, reference):
            self.assertGreater(sum(a * b for a, b in zip(got, want)), 0.99999)

    def test_stored_embeddings_represent_every_trecho_with_current_strategy(self):
        encoder = self.retriever.encoder
        with self.driver.session() as session:
            rows = session.run(
                "MATCH (t:Trecho) RETURN t.trecho_id AS id, t.texto AS texto, size(t.embedding) AS dim, "
                "sqrt(reduce(s = 0.0, x IN t.embedding | s + x * x)) AS norma, t.embedding_windows AS janelas, "
                "t.embedding_pipeline_version AS versao, t.embedding_model AS modelo"
            ).data()
        self.assertEqual(len(rows), 54)
        for row in rows:
            plan = encoder.window_plan(row["texto"])
            with self.subTest(trecho=row["id"]):
                self.assertEqual((row["dim"], row["modelo"]), (EMBEDDING_DIMENSIONS, MODEL_NAME))
                self.assertEqual(row["versao"], EMBEDDING_PIPELINE_VERSION,
                                 "embedding de outra versão: rode scripts/generate_embeddings.py")
                self.assertAlmostEqual(row["norma"], 1.0, places=4)
                self.assertEqual(row["janelas"], len(plan["janelas"]))
                self.assertEqual(plan["tokens_nao_representados"], 0)

    def test_outdated_strategy_version_is_selected_for_regeneration(self):
        """Simula vetores de versão antiga dentro de uma transação desfeita ao final."""
        generator = load_generator()
        params = {"force": False, "model": MODEL_NAME, "version": EMBEDDING_PIPELINE_VERSION}
        with self.driver.session() as session:
            tx = session.begin_transaction()
            try:
                ids = [r["id"] for r in tx.run("MATCH (t:Trecho) RETURN t.trecho_id AS id ORDER BY id LIMIT 2")]
                tx.run("MATCH (t:Trecho {trecho_id: $id}) SET t.embedding_pipeline_version = 'v1-antigo'", id=ids[0])
                tx.run("MATCH (t:Trecho {trecho_id: $id}) REMOVE t.embedding_pipeline_version", id=ids[1])
                pending = {r["trecho_id"]: r["motivo"] for r in tx.run(generator.SELECT_PENDING, params)}
            finally:
                tx.rollback()
            after = session.run(generator.SELECT_PENDING, params).data()
        self.assertEqual(pending, {ids[0]: "versao_antiga", ids[1]: "versao_antiga"})
        self.assertEqual(after, [])

    def test_company_paths_on_real_data_are_structural_by_cnae(self):
        result = self.retriever.company_paths("00356328", "01340937")
        self.assertEqual(validate_company_paths_response(result), [])
        self.assertEqual([(p["kind"], p["length"]) for p in result["paths"]], [("atividade_cnae", 4)])
        self.assertIn("CNAE:4211101", result["paths"][0]["nodes"])
        self.assertTrue(any("Nenhum caminho societário" in w for w in result["warnings"]))
        self.assertTrue(any("atividade econômica declarada em comum" in w for w in result["warnings"]))


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_embeddings", ROOT / "scripts" / "generate_embeddings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
