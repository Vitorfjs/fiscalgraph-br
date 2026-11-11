"""Cenário SINTÉTICO de multi-hop (dev5) — não faz parte do recorte real.

O recorte canônico não tem o padrão Empresa A <- Socio -> Empresa B (socio_id tem escopo por
empresa). Este teste executa o bloco ``<cenario-sintetico>`` de ``cypher/03_multi_hop.cypher``,
que cria nós :Sintetico, calcula o shortestPath e os apaga na mesma instrução. Aqui o bloco ainda
roda dentro de uma transação explícita com rollback: nada persiste no banco.

O teste de integração exige Neo4j ativo e NEO4J_PASSWORD (variável de ambiente ou ``.env``);
sem isso ele é ignorado (skip). A checagem do arquivo roda sempre.

Executar na raiz do repositório:
    python -m unittest discover -s tests -p "test_multi_hop_sintetico.py" -v
"""
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CYPHER_FILE = ROOT / "cypher" / "03_multi_hop.cypher"
START, END = "// <cenario-sintetico>", "// </cenario-sintetico>"


def synthetic_statement() -> str:
    text = CYPHER_FILE.read_text(encoding="utf-8")
    block = text[text.index(START) + len(START):text.index(END)]
    return block.strip().rstrip(";")


class SyntheticBlockTests(unittest.TestCase):
    def test_every_created_node_is_marked_synthetic(self):
        statement = synthetic_statement()
        created = re.findall(r"\((\w+):([\w:]+) \{([^}]*)\}", statement)
        self.assertEqual(len(created), 3)
        for _, labels, properties in created:
            self.assertIn("Sintetico", labels.split(":"))
            self.assertIn("sintetico: true", properties)
            self.assertIn("'SINT-", properties)

    def test_block_cleans_up_and_uses_shortest_path(self):
        statement = synthetic_statement()
        self.assertIn("shortestPath((a)-[:PARTICIPA_DE*..6]-(b))", statement)
        self.assertIn("DETACH DELETE a, b, s", statement)


class SyntheticMultiHopNeo4jTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from dotenv import load_dotenv
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise unittest.SkipTest(f"dependência ausente: {exc}")
        load_dotenv(ROOT / ".env")
        password = os.getenv("NEO4J_PASSWORD")
        if not password or password == "change_this_password_before_starting":
            raise unittest.SkipTest("NEO4J_PASSWORD não configurado; teste de integração ignorado.")
        cls.database = os.getenv("NEO4J_DATABASE", "neo4j")
        cls.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), password),
        )
        try:
            cls.driver.verify_connectivity()
        except Exception as exc:  # banco desligado ou credencial errada
            cls.driver.close()
            raise unittest.SkipTest(f"Neo4j inacessível: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()

    def count_synthetic(self, session) -> int:
        return session.run("MATCH (n) WHERE n:Sintetico OR n.sintetico = true RETURN count(n) AS c").single()["c"]

    def test_shortest_path_through_synthetic_partner_leaves_no_trace(self):
        with self.driver.session(database=self.database) as session:
            self.assertEqual(self.count_synthetic(session), 0, "há nós sintéticos esquecidos no banco")
            tx = session.begin_transaction()
            try:
                record = tx.run(synthetic_statement()).single()
            finally:
                tx.rollback()
            remaining = self.count_synthetic(session)

        self.assertEqual(record["cenario"], "SINTETICO")
        self.assertEqual(record["nos"], ["Empresa:SINT-EMP-A", "Socio:SINT-SOC-1", "Empresa:SINT-EMP-B"])
        self.assertEqual(record["relacionamentos"], ["PARTICIPA_DE", "PARTICIPA_DE"])
        self.assertEqual(record["quantidade_relacionamentos"], 2)
        self.assertEqual(remaining, 0)

    def test_company_paths_service_classifies_synthetic_partner_as_societal(self):
        """O serviço company_paths sobre o mesmo cenário sintético, criado e desfeito na transação."""
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from app.services.contract import validate_company_paths_response
        from app.services.multi_hop import find_company_paths

        create = """
        CREATE (a:Empresa:Sintetico {cnpj_basico: 'SINT-EMP-A', razao_social: 'EMPRESA SINTETICA A', sintetico: true}),
               (b:Empresa:Sintetico {cnpj_basico: 'SINT-EMP-B', razao_social: 'EMPRESA SINTETICA B', sintetico: true}),
               (s:Socio:Sintetico {socio_id: 'SINT-SOC-1', tipo_pessoa: 'PESSOA JURIDICA', sintetico: true}),
               (s)-[:PARTICIPA_DE {registro_origem: 'SINTETICO'}]->(a),
               (s)-[:PARTICIPA_DE {registro_origem: 'SINTETICO'}]->(b)
        """
        with self.driver.session(database=self.database) as session:
            tx = session.begin_transaction()
            try:
                tx.run(create).consume()
                result = find_company_paths(tx, "SINT-EMP-A", "SINT-EMP-B")
            finally:
                tx.rollback()
            remaining = self.count_synthetic(session)

        self.assertEqual(validate_company_paths_response(result), [])
        self.assertEqual([(p["kind"], p["length"]) for p in result["paths"]], [("societario", 2)])
        self.assertEqual(result["paths"][0]["nodes"], ["Empresa:SINT-EMP-A", "Socio:SINT-SOC-1", "Empresa:SINT-EMP-B"])
        self.assertFalse(any("Nenhum caminho societário" in w for w in result["warnings"]))
        self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
