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

from app.services.contract import validate_retrieval_response  # noqa: E402
from app.services.embeddings import EMBEDDING_DIMENSIONS  # noqa: E402

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

    def test_formatted_cnpj_is_found_by_fulltext(self):
        chunks = self.results["trecho que cita o CNPJ 01.340.937/0001-79"]["chunks"]
        self.assertEqual((chunks[0]["registro_id"], chunks[0]["fulltext_rank"]), ("CEIS-289814", 1))

    def test_out_of_scope_question_is_flagged(self):
        result = self.results[OUT_OF_SCOPE]
        self.assertTrue(all(c["fulltext_rank"] is None for c in result["chunks"]))
        self.assertTrue(any("Nenhum termo da pergunta" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
