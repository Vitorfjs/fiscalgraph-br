import json
import os
from pathlib import Path

def get_mock_response(cenario="sucesso"):
    """
    Simula a chamada ao serviço do Dev1. 
    Retorna a fixture correspondente ao cenário escolhido.
    """
    # Navega até a pasta raiz e depois para fixtures
    base_path = Path(__file__).resolve().parents[2] / "fixtures"
    
    if cenario == "sucesso":
        filename = "resposta_completa_mock.json"
    else:
        filename = "resposta_abstencao_mock.json"
        
    filepath = base_path / filename
    
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)