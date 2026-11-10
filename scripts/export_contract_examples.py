#!/usr/bin/env python3
"""Exporta exemplos do contrato do dev5 a partir de execuções reais no Neo4j.

Arquivos gerados (todos validados antes de gravar):

- ``docs/evidencias/dev5_retrieve_context_exemplo.json``: resposta REAL de ``retrieve_context``;
- ``docs/evidencias/dev5_company_paths_exemplo.json``: resposta REAL de ``company_paths``;
- ``docs/exemplos/resposta_final_dev1.exemplo.json``: EXEMPLO DEMONSTRATIVO da resposta final do
  dev1, montado com ``example_final_response`` sobre a resposta real. O ``answer`` é um texto fixo
  deste script, não gerado por LLM, e serve só para o dev6 testar a interface.

Requer ``.env`` local, Neo4j ativo e embeddings gerados.

Uso:
    python scripts/export_contract_examples.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QUESTION = "trecho que cita o CNPJ 01.340.937/0001-79"
TOP_K = 2
COMPANIES = ("00356328", "01340937")
EVIDENCE_DIR = ROOT / "docs" / "evidencias"
EXAMPLES_DIR = ROOT / "docs" / "exemplos"


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"gravado: {path.relative_to(ROOT)}")


def main() -> int:
    from app.services.contract import (
        example_final_response,
        validate_company_paths_response,
        validate_retrieval_response,
    )
    from app.services.retrieval import GraphHybridRetriever

    retriever = GraphHybridRetriever.from_env()
    try:
        context = retriever.retrieve_context(QUESTION, top_k=TOP_K)
        paths = retriever.company_paths(*COMPANIES)
    finally:
        retriever.close()

    problems = {"retrieve_context": validate_retrieval_response(context),
                "company_paths": validate_company_paths_response(paths)}
    # Segue a orientação da seção 7.3: com CNPJ na pergunta, a evidência principal é o trecho que o
    # contém literalmente (identifier_matches), não necessariamente o 1º do RRF.
    chunks = context["chunks"]
    top = next((c for c in chunks if c["identifier_matches"]), chunks[0] if chunks else None)
    answer = (
        "[EXEMPLO DEMONSTRATIVO — texto fixo do script, não gerado por LLM] "
        + (f"Evidência principal: registro {top['registro_id']} da fonte {top['fonte_id']}"
           + (f", que contém literalmente o CNPJ {', '.join(top['identifier_matches'])}" if top["identifier_matches"] else "")
           + ". Consulte as fontes e os caminhos do grafo antes de qualquer conclusão." if top else
           "Não há evidência suficiente no recorte.")
    )
    final = {
        "_aviso": ("EXEMPLO DEMONSTRATIVO para o dev6 testar a interface. Não é resposta real do sistema: "
                   "'answer' é texto fixo, não gerado por LLM, e 'abstained'/'retrieval_relevance' seguem "
                   "apenas o mapeamento de referência; a regra final é do dev1."),
        "_origem": {"pergunta": QUESTION, "top_k": TOP_K,
                    "gerado_por": "scripts/export_contract_examples.py (example_final_response)"},
        **example_final_response(context, answer=answer),
    }
    for name, found in problems.items():
        print(f"{name}: {'OK (0 violações)' if not found else found}")
    if any(problems.values()):
        return 1
    write_json(EVIDENCE_DIR / "dev5_retrieve_context_exemplo.json", context)
    write_json(EVIDENCE_DIR / "dev5_company_paths_exemplo.json", paths)
    write_json(EXAMPLES_DIR / "resposta_final_dev1.exemplo.json", final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
