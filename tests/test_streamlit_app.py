import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import streamlit as st
from neo4j.exceptions import AuthError, ServiceUnavailable
from streamlit.testing.v1 import AppTest

from app import streamlit_app
from app.services import orchestrator, retrieval, ui_helpers

APP_PATH = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


class StreamlitHelpersTests(unittest.TestCase):
    def test_build_graph_elements_styles_nodes_filters_dangling_edges_and_marks_candidates(self):
        nodes_data = [
            {"id": "n-emp", "label": "Empresa", "properties": {"cnpj_basico": "01340937", "razao_social": "Alfa Ltda"}},
            {"id": "n-tr", "label": "Trecho", "properties": {"trecho_id": "TR-1"}},
            {"id": "n-est", "label": "Estabelecimento", "properties": {"cnpj": "01340937000179"}},
        ]
        relationships_data = [
            {"source": "n-tr", "target": "n-est", "type": "MENCIONA", "properties": {"status": "CANDIDATA"}},
            {"source": "n-tr", "target": "n-emp", "type": "MENCAO_NOME", "properties": {"status": "CANDIDATA"}},
            {"source": "n-emp", "target": "n-est", "type": "POSSUI_ESTABELECIMENTO", "properties": {}},
            {"source": "n-tr", "target": "missing-node", "type": "ORIGINADO_DE", "properties": {}},
        ]

        graph_nodes, graph_edges, candidate_count = ui_helpers.build_graph_elements(
            nodes_data, relationships_data
        )

        self.assertEqual(len(graph_nodes), 3)
        self.assertEqual(len(graph_edges), 3)
        self.assertEqual(candidate_count, 2)

        colors_by_id = {node.id: node.color for node in graph_nodes}
        self.assertNotEqual(colors_by_id["n-emp"], colors_by_id["n-tr"])

        candidate_edge = next(edge for edge in graph_edges if edge.label == "MENCIONA (CANDIDATA)")
        candidate_name_edge = next(edge for edge in graph_edges if edge.label == "MENCAO_NOME (CANDIDATA)")
        confirmed_edge = next(edge for edge in graph_edges if edge.label == "POSSUI_ESTABELECIMENTO")
        self.assertEqual(candidate_edge.color, "#FF4B4B")
        self.assertTrue(candidate_edge.dashes)
        self.assertEqual(candidate_name_edge.color, "#FF4B4B")
        self.assertTrue(candidate_name_edge.dashes)
        self.assertEqual(confirmed_edge.color, "#4A90E2")
        self.assertFalse(confirmed_edge.dashes)

    def test_sanitize_error_message_masks_sensitive_env_values(self):
        sanitized = ui_helpers.sanitize_error_message(
            "Falha ao conectar com senha_local_123 e sk-secret-abc",
            secrets=["senha_local_123", "sk-secret-abc", ""],
        )
        self.assertNotIn("senha_local_123", sanitized)
        self.assertNotIn("sk-secret-abc", sanitized)
        self.assertIn("***", sanitized)

    def test_check_neo4j_status_handles_missing_placeholder_auth_unavailable_and_connected(self):
        missing = ui_helpers.check_neo4j_status("bolt://localhost:7687", "neo4j", "")
        self.assertEqual(missing["state"], "missing_password")

        placeholder = ui_helpers.check_neo4j_status(
            "bolt://localhost:7687", "neo4j", "change_this_password_before_starting"
        )
        self.assertEqual(placeholder["state"], "missing_password")

        with patch.object(ui_helpers.GraphDatabase, "driver") as mock_driver_cls:
            mock_driver = mock_driver_cls.return_value.__enter__.return_value
            mock_driver.verify_connectivity.side_effect = AuthError("unauthorized")
            auth_res = ui_helpers.check_neo4j_status("bolt://localhost:7687", "neo4j", "segredo")
        self.assertEqual(auth_res["state"], "auth_error")

        with patch.object(ui_helpers.GraphDatabase, "driver") as mock_driver_cls:
            mock_driver = mock_driver_cls.return_value.__enter__.return_value
            mock_driver.verify_connectivity.side_effect = ServiceUnavailable("down")
            down_res = ui_helpers.check_neo4j_status("bolt://localhost:7687", "neo4j", "segredo")
        self.assertEqual(down_res["state"], "unavailable")

        with patch.object(ui_helpers.GraphDatabase, "driver") as mock_driver_cls:
            mock_driver = mock_driver_cls.return_value.__enter__.return_value
            mock_session = mock_driver.session.return_value.__enter__.return_value
            mock_session.run.return_value.single.return_value = {"nodes": 210, "relationships": 405}
            ok_res = ui_helpers.check_neo4j_status("bolt://localhost:7687", "neo4j", "segredo", "neo4j")

        self.assertEqual(ok_res["state"], "connected")
        self.assertEqual(ok_res["nodes"], 210)
        self.assertEqual(ok_res["relationships"], 405)
        cypher_used = mock_session.run.call_args[0][0]
        self.assertIn("CALL () {", cypher_used)
        self.assertIs(streamlit_app.build_graph_elements, ui_helpers.build_graph_elements)


class StreamlitAppUITests(unittest.TestCase):
    def setUp(self):
        st.cache_resource.clear()

    def tearDown(self):
        st.cache_resource.clear()

    def _connected_status(self, *args, **kwargs):
        return {"state": "connected", "nodes": 210, "relationships": 405, "message": "Conectado"}

    def _new_app(self):
        return AppTest.from_file(APP_PATH, default_timeout=15)

    def test_initial_render_shows_disclaimer_status_and_controls(self):
        with patch.object(ui_helpers, "check_neo4j_status", side_effect=self._connected_status):
            at = self._new_app()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual([t.value for t in at.title], ["FiscalGraph BR"])
        self.assertTrue(any("Protótipo acadêmico" in info.value for info in at.info))
        self.assertTrue(any(metric.label == "Nós" and metric.value == "210" for metric in at.metric))
        self.assertTrue(any(metric.label == "Relacionamentos" and metric.value == "405" for metric in at.metric))
        self.assertTrue(any("pressione Pesquisar" in cap.value for cap in at.caption))

    def test_empty_submission_displays_warning(self):
        with patch.object(ui_helpers, "check_neo4j_status", side_effect=self._connected_status):
            at = self._new_app()
            at.run()
            at.text_input[0].input("   ")
            at.button[0].click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Digite uma pergunta antes de pesquisar." in w.value for w in at.warning))

    def test_mock_success_mode_renders_answer_sources_cypher_and_graph_metrics(self):
        with patch.object(ui_helpers, "check_neo4j_status", side_effect=self._connected_status):
            at = self._new_app()
            at.run()
            at.sidebar.radio[0].set_value("Demonstração (Mock)").run()
            at.sidebar.radio[1].set_value("Sucesso (grafo e fontes)")
            at.text_input[0].input("Teste de demonstração")
            at.button[0].click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Resposta demonstrativa" in s.value for s in at.success))
        self.assertTrue(any("Fixture sintética" in w.value for w in at.warning))
        self.assertTrue(any("Fontes e evidências utilizadas (1)" == exp.label for exp in at.expander))
        self.assertTrue(any("Consulta Cypher" == exp.label for exp in at.expander))
        self.assertTrue(any("Relevância normalizada da recuperação: 0.820" in c.value for c in at.caption))
        self.assertTrue(any(m.label == "Menções candidatas" and m.value == "1" for m in at.metric))

    def test_mock_abstention_mode_renders_error_and_no_subgraph(self):
        with patch.object(ui_helpers, "check_neo4j_status", side_effect=self._connected_status):
            at = self._new_app()
            at.run()
            at.sidebar.radio[0].set_value("Demonstração (Mock)").run()
            at.sidebar.radio[1].set_value("Abstenção (sem conclusão)")
            at.text_input[0].input("Teste de abstenção")
            at.button[0].click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.error), 1)
        self.assertTrue(any("Nenhum subgrafo foi retornado para esta consulta." in i.value for i in at.info))
        self.assertFalse(any("Fontes e evidências utilizadas" in exp.label for exp in at.expander))

    def test_real_mode_success_renders_answer_sources_candidate_edge_and_top_k(self):
        fake_retriever = MagicMock()
        fake_payload = {
            "answer": "A recuperação encontrou 1 trecho(s) potencialmente relevante(s).",
            "cypher": "MATCH (t:Trecho)-[r:MENCIONA]->(e:Estabelecimento) RETURN t, r, e",
            "sources": [
                {
                    "id": "CEIS-289814",
                    "label": "Sancao",
                    "url": "https://portaldatransparencia.gov.br/sancoes/ceis",
                    "excerpt": "CNPJ 01.340.937/0001-79 citado no trecho.",
                },
                {
                    "id": "TR-SEM-URL",
                    "label": "Trecho",
                    "url": None,
                    "excerpt": "Trecho sem link externo.",
                },
            ],
            "nodes": [
                {"id": "tr-1", "label": "Trecho", "properties": {"trecho_id": "TR-1"}},
                {"id": "est-1", "label": "Estabelecimento", "properties": {"cnpj": "01340937000179"}},
            ],
            "relationships": [
                {
                    "source": "tr-1",
                    "target": "est-1",
                    "type": "MENCIONA",
                    "properties": {"status": "CANDIDATA"},
                }
            ],
            "retrieval_relevance": 0.992,
            "abstained": False,
            "warnings": ["A relação MENCIONA está em estado CANDIDATA."],
        }

        with (
            patch.object(ui_helpers, "check_neo4j_status", side_effect=self._connected_status),
            patch.object(retrieval.GraphHybridRetriever, "from_env", return_value=fake_retriever),
            patch.object(orchestrator, "answer_question", return_value=fake_payload) as mock_answer,
        ):
            at = self._new_app()
            at.run()
            at.sidebar.slider[0].set_value(7)
            at.text_input[0].input("Qual a situação do CNPJ 01.340.937/0001-79?")
            at.button[0].click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        mock_answer.assert_called_once_with(
            "Qual a situação do CNPJ 01.340.937/0001-79?",
            top_k=7,
            retriever=fake_retriever,
        )
        self.assertTrue(any("A recuperação encontrou 1 trecho(s)" in s.value for s in at.success))
        self.assertTrue(any("Fontes e evidências utilizadas (2)" == exp.label for exp in at.expander))
        self.assertTrue(any(m.label == "Menções candidatas" and m.value == "1" for m in at.metric))
        self.assertTrue(any("URL não informada" in c.value for c in at.caption))

    def test_real_mode_abstention_renders_error_without_sources_or_graph(self):
        fake_payload = {
            "answer": "A pergunta está fora do escopo do FiscalGraph BR.",
            "cypher": "",
            "sources": [],
            "nodes": [],
            "relationships": [],
            "retrieval_relevance": None,
            "abstained": True,
            "warnings": ["Fora de domínio."],
        }

        with (
            patch.object(ui_helpers, "check_neo4j_status", side_effect=self._connected_status),
            patch.object(retrieval.GraphHybridRetriever, "from_env", return_value=MagicMock()),
            patch.object(orchestrator, "answer_question", return_value=fake_payload),
        ):
            at = self._new_app()
            at.run()
            at.text_input[0].input("receita de bolo de chocolate")
            at.button[0].click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("fora do escopo" in e.value for e in at.error))
        self.assertTrue(any("Nenhum subgrafo foi retornado para esta consulta." in i.value for i in at.info))
        self.assertFalse(any("Fontes e evidências utilizadas" in exp.label for exp in at.expander))

    def test_real_mode_connection_error_shows_safe_technical_details(self):
        with (
            patch.dict(os.environ, {"NEO4J_PASSWORD": "segredo_ultra_protegido"}, clear=False),
            patch.object(
                ui_helpers,
                "check_neo4j_status",
                return_value={
                    "state": "unavailable",
                    "message": "Neo4j indisponível. Inicie o serviço e confira NEO4J_URI.",
                },
            ),
            patch.object(
                retrieval.GraphHybridRetriever,
                "from_env",
                side_effect=RuntimeError("Falha ao conectar usando segredo_ultra_protegido"),
            ),
        ):
            at = self._new_app()
            at.run()
            at.text_input[0].input("Quais empresas têm sanção?")
            at.button[0].click()
            at.run()

        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Neo4j indisponível" in e.value for e in at.error))
        self.assertTrue(any("Não foi possível executar a consulta real." in e.value for e in at.error))
        self.assertTrue(any("Detalhes técnicos" == exp.label for exp in at.expander))
        code_texts = [c.value for c in at.code]
        self.assertTrue(any("***" in text and "segredo_ultra_protegido" not in text for text in code_texts))


if __name__ == "__main__":
    unittest.main()
