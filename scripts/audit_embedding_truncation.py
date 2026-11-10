#!/usr/bin/env python3
"""Audita quanto do texto de cada Trecho cabe no limite de tokens do modelo de embeddings (dev5).

Lê ``data/processed/trechos.jsonl`` (dev4) e ``data/processed/canonical/compliance.csv`` (dev2),
usa o tokenizador do próprio modelo e mostra:

1. de onde vem o limite (configuração do modelo x capacidade da arquitetura);
2. a distribuição de tokens dos trechos e quantos passam do limite;
3. quanto cada campo do texto (descricao, observacoes, fundamentacao_legal) contribui;
4. por que texto em caixa alta rende mais tokens;
5. onde o corte acontece num trecho de exemplo.

Os textos são recompostos com as mesmas funções do dev4 (``compose_text`` e ``mask_cpf``) e
comparados com os de ``trechos.jsonl``. Não acessa o Neo4j e não grava nada.

Uso:
    python scripts/audit_embedding_truncation.py
    python scripts/audit_embedding_truncation.py --registro CEIS-132342
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Callable, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.text_to_graph.extractor import TEXT_FIELDS, compose_text, mask_cpf  # noqa: E402

TRECHOS = ROOT / "data" / "processed" / "trechos.jsonl"
COMPLIANCE = ROOT / "data" / "processed" / "canonical" / "compliance.csv"
CASE_EXAMPLES = ("administração", "ADMINISTRAÇÃO", "inidoneidade", "INIDONEIDADE", "contratado", "CONTRATADO")


def embedded_text(record: Dict[str, str]) -> str:
    """Texto exatamente como o dev4 grava no Trecho (campos concatenados e CPF mascarado)."""
    return mask_cpf(compose_text(record))[0]


def field_report(records: List[Dict[str, str]], count: Callable[[str], int], limit: int,
                 special_tokens: int) -> Dict[str, object]:
    """Contribuição de cada campo e quantos textos passariam do limite com e sem a fundamentação.

    ``count`` devolve tokens sem os especiais; ``special_tokens`` ocupa posições do limite.
    """
    over = lambda text: count(text) + special_tokens > limit  # noqa: E731
    fields = {}
    for field, _ in TEXT_FIELDS:
        sizes = [count((r.get(field) or "").strip()) for r in records]
        fields[field] = {
            "mediana": statistics.median(sizes) if sizes else None,
            "maximo": max(sizes) if sizes else None,
            "vazios": sum(1 for size in sizes if size == 0),
        }
    without_legal = [dict(r, fundamentacao_legal="") for r in records]
    return {
        "registros": len(records),
        "campos": fields,
        "acima_com_texto_completo": sum(1 for r in records if over(embedded_text(r))),
        "acima_sem_fundamentacao_legal": sum(1 for r in without_legal if over(embedded_text(r))),
        "fundamentacao_legal_sozinha_acima": sum(
            1 for r in records if over((r.get("fundamentacao_legal") or "").strip())),
    }


def load_records() -> tuple:
    trechos = {}
    for line in TRECHOS.open(encoding="utf-8"):
        if line.strip():
            item = json.loads(line)
            trechos[item["registro_id"]] = item
    with COMPLIANCE.open(encoding="utf-8-sig", newline="") as handle:
        records = [row for row in csv.DictReader(handle) if row.get("registro_id") in trechos]
    return trechos, records


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audita o truncamento dos trechos no modelo de embeddings.")
    parser.add_argument("--registro", default="CEIS-132342", help="registro_id usado no exemplo de corte")
    args = parser.parse_args(argv)

    from app.services.embeddings import MODEL_NAME, SentenceEncoder, truncation_summary

    encoder = SentenceEncoder()
    tokenizer = encoder.model.tokenizer
    limit = encoder.max_seq_length
    special = tokenizer.num_special_tokens_to_add(pair=False)
    arch = getattr(encoder.model[0], "auto_model", None)
    arch_limit = getattr(getattr(arch, "config", None), "max_position_embeddings", None)

    def count(text: str) -> int:
        return len(tokenizer(text, add_special_tokens=False, verbose=False)["input_ids"]) if text else 0

    trechos, records = load_records()
    texts = [item["texto"] for item in trechos.values()]

    print(f"Modelo: {MODEL_NAME}")
    print("1. Origem do limite")
    print(f"   max_seq_length = {limit} tokens (sentence_bert_config.json do modelo; é o valor que o "
          "sentence-transformers usa para cortar o texto)")
    print(f"   max_position_embeddings = {arch_limit} (config.json da arquitetura: capacidade máxima, "
          "não o tamanho de trabalho do modelo)")
    print(f"   tokens especiais por texto = {special} (início e fim); sobram {limit - special} para o conteúdo")

    summary = truncation_summary(encoder.count_tokens(texts), limit)
    print("\n2. Trechos (data/processed/trechos.jsonl)")
    print(f"   total = {summary['total']} | cabem inteiros = {summary['total'] - summary['acima_do_limite']} | "
          f"truncados = {summary['acima_do_limite']}")
    print(f"   tokens por trecho: mín. {summary['minimo']} | mediana {summary['mediana']:g} | máx. {summary['maximo']}")
    words = [len(text.split()) for text in texts]
    ratio = statistics.median(count(text) / max(1, len(text.split())) for text in texts)
    print(f"   palavras por trecho (mediana) = {statistics.median(words):g} | tokens por palavra (mediana) = {ratio:.2f}")

    same = sum(1 for r in records if embedded_text(r) == trechos[r["registro_id"]]["texto"])
    report = field_report(records, count, limit, special)
    print("\n3. Contribuição de cada campo (compliance.csv, mesma composição do dev4)")
    print(f"   textos recompostos idênticos aos de trechos.jsonl: {same}/{report['registros']}")
    for field, stats in report["campos"].items():
        print(f"   {field:20s} mediana {stats['mediana']:>6g} | máx. {stats['maximo']:>4} | vazio em {stats['vazios']}")
    print(f"   acima do limite com o texto completo: {report['acima_com_texto_completo']}/{report['registros']}")
    print(f"   acima do limite sem fundamentacao_legal: {report['acima_sem_fundamentacao_legal']}/{report['registros']}")
    print(f"   fundamentacao_legal sozinha já passa do limite: {report['fundamentacao_legal_sozinha_acima']}/"
          f"{report['registros']}")

    print("\n4. Caixa alta x minúsculas (pedaços de palavra no vocabulário do modelo)")
    for word in CASE_EXAMPLES:
        pieces = tokenizer.tokenize(word)
        print(f"   {word:14s} {len(pieces)} token(s): {' '.join(pieces)}")

    example = trechos.get(args.registro)
    if example:
        ids = tokenizer(example["texto"], verbose=False)["input_ids"]
        read = tokenizer.decode(ids[1:limit - 1])
        ignored = tokenizer.decode(ids[limit - 1:-1])
        print(f"\n5. Exemplo de corte: {args.registro} ({len(example['texto'].split())} palavras, {len(ids)} tokens)")
        print(f"   últimas palavras lidas: …{read[-100:]}")
        print(f"   primeiras palavras ignoradas: {ignored[:100]}…" if ignored else "   nada é ignorado")
        print(f"   tokens ignorados: {max(0, len(ids) - limit)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
