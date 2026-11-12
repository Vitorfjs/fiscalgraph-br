#!/usr/bin/env python3
"""Executa avaliação quantitativa da recuperação híbrida, abstenção e multi-hop no Neo4j real."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.benchmark import format_benchmark_markdown, run_benchmark_against_neo4j
from app.services.retrieval import GraphHybridRetriever

DEFAULT_DATASET = ROOT / "data" / "fixtures" / "retrieval_benchmark.json"
DEFAULT_JSON_OUT = ROOT / "docs" / "evidencias" / "dev5_benchmark_metricas.json"
DEFAULT_MD_OUT = ROOT / "docs" / "evidencias" / "dev5_benchmark_recuperacao.md"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Avalia Vetorial vs. Full-text vs. Híbrido RRF, Abstenção e Multi-hop no Neo4j."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD_OUT)
    args = parser.parse_args(argv)

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    retriever = GraphHybridRetriever.from_env()
    try:
        report = run_benchmark_against_neo4j(retriever, dataset, k=args.k)
    finally:
        retriever.close()

    markdown = format_benchmark_markdown(report)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(markdown + "\n", encoding="utf-8")

    print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
