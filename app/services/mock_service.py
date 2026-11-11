import json
from pathlib import Path


def get_mock_response(cenario: str = "sucesso"):
    """Carrega fixture sintética para demonstração da interface."""
    fixtures_dir = Path(__file__).resolve().parents[2] / "fixtures"
    filename = "resposta_completa_mock.json" if cenario == "sucesso" else "resposta_abstencao_mock.json"
    with (fixtures_dir / filename).open("r", encoding="utf-8") as file:
        return json.load(file)
