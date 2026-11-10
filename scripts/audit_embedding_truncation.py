#!/usr/bin/env python3
"""Audita quanto do texto de cada Trecho é representado no embedding (dev5).

Lê ``data/processed/trechos.jsonl`` (dev4) e ``data/processed/canonical/compliance.csv`` (dev2),
usa o tokenizador do próprio modelo e mostra:

1. de onde vem o limite (configuração do modelo x capacidade da arquitetura) e o limite efetivo;
2. a distribuição de tokens dos trechos;
3. quanto cada campo do texto (descricao, observacoes, fundamentacao_legal) contribui;
4. por que texto em caixa alta rende mais tokens;
5. a estratégia anterior (truncamento) x a atual (janelas): janelas usadas e tokens não representados;
6. num trecho de exemplo, onde o truncamento cortava e quais janelas cobrem o texto até o fim.

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
    parser = argparse.ArgumentParser(description="Audita a representação dos trechos no embedding.")
    parser.add_argument("--registro", default="CEIS-132342", help="registro_id usado no exemplo")
    args = parser.parse_args(argv)

    from app.services.embeddings import EMBEDDING_PIPELINE_VERSION, MODEL_NAME, SentenceEncoder

    encoder = SentenceEncoder()
    tokenizer = encoder.tokenizer
    previous_limit = encoder.default_max_seq_length  # truncamento da estratégia anterior
    special = encoder.special_tokens

    def count(text: str) -> int:
        return len(encoder.content_token_ids(text)) if text else 0

    trechos, records = load_records()
    texts = [item["texto"] for item in trechos.values()]
    sizes = [count(text) for text in texts]

    print(f"Modelo: {MODEL_NAME}")
    print("1. Origem do limite")
    print(f"   max_seq_length padrão = {previous_limit} tokens (sentence_bert_config.json do modelo; "
          "o sentence-transformers corta o texto nesse tamanho)")
    print(f"   max_position_embeddings = {encoder.architecture_limit} (config.json da arquitetura: capacidade máxima)")
    print(f"   tokens especiais por janela = {special} (início e fim)")
    print(f"   limite efetivo por janela na estratégia atual = {encoder.window_tokens} tokens de conteúdo "
          f"+ {special} especiais = {encoder.max_seq_length} posições; sobreposição = {encoder.overlap}")

    print("\n2. Trechos (data/processed/trechos.jsonl)")
    print(f"   total = {len(texts)} | tokens de conteúdo por trecho: mín. {min(sizes)} | "
          f"mediana {statistics.median(sizes):g} | máx. {max(sizes)}")
    words = [len(text.split()) for text in texts]
    ratio = statistics.median(count(text) / max(1, len(text.split())) for text in texts)
    print(f"   palavras por trecho (mediana) = {statistics.median(words):g} | tokens por palavra (mediana) = {ratio:.2f}")

    same = sum(1 for r in records if embedded_text(r) == trechos[r["registro_id"]]["texto"])
    report = field_report(records, count, previous_limit, special)
    print(f"\n3. Contribuição de cada campo (compliance.csv, mesma composição do dev4; limite de {previous_limit})")
    print(f"   textos recompostos idênticos aos de trechos.jsonl: {same}/{report['registros']}")
    for field, stats in report["campos"].items():
        print(f"   {field:20s} mediana {stats['mediana']:>6g} | máx. {stats['maximo']:>4} | vazio em {stats['vazios']}")
    print(f"   acima de {previous_limit} com o texto completo: {report['acima_com_texto_completo']}/{report['registros']}")
    print(f"   acima de {previous_limit} sem fundamentacao_legal: {report['acima_sem_fundamentacao_legal']}/{report['registros']}")
    print(f"   fundamentacao_legal sozinha acima de {previous_limit}: {report['fundamentacao_legal_sozinha_acima']}/"
          f"{report['registros']}")

    print("\n4. Caixa alta x minúsculas (pedaços de palavra no vocabulário do modelo)")
    for word in CASE_EXAMPLES:
        pieces = tokenizer.tokenize(word)
        print(f"   {word:14s} {len(pieces)} token(s): {' '.join(pieces)}")

    previous_content = previous_limit - special
    plans = [encoder.window_plan(text) for text in texts]
    windows = [len(plan["janelas"]) for plan in plans]
    print("\n5. Representação no embedding: estratégia anterior x atual")
    print(f"   anterior (truncamento em {previous_limit}): 1 trecho = 1 passada; trechos com tokens descartados = "
          f"{sum(1 for n in sizes if n > previous_content)}/{len(sizes)}; tokens não representados = "
          f"{sum(max(0, n - previous_content) for n in sizes)}")
    print(f"   atual ({EMBEDDING_PIPELINE_VERSION}):")
    print(f"     janelas = {sum(windows)} (1 janela: {sum(1 for w in windows if w == 1)} trechos; "
          f"mais de uma: {sum(1 for w in windows if w > 1)}; máx. {max(windows)} por trecho)")
    print(f"     trechos representados integralmente = "
          f"{sum(1 for plan in plans if plan['tokens_nao_representados'] == 0)}/{len(plans)} | "
          f"tokens não representados = {sum(plan['tokens_nao_representados'] for plan in plans)}")
    print("     agregação: média dos vetores das janelas ponderada pelos tokens novos de cada janela, "
          "normalizada em L2 (1 vetor de 384 dimensões por Trecho)")

    example = trechos.get(args.registro)
    if example:
        ids = encoder.content_token_ids(example["texto"])
        plan = encoder.window_plan(example["texto"])
        print(f"\n6. Exemplo: {args.registro} ({len(example['texto'].split())} palavras, {len(ids)} tokens de conteúdo)")
        print(f"   truncamento anterior lia até: …{tokenizer.decode(ids[:previous_content])[-80:]}")
        print(f"   e descartava {max(0, len(ids) - previous_content)} tokens a partir de: "
              f"{tokenizer.decode(ids[previous_content:previous_content + 20])}…")
        print(f"   estratégia atual: {len(plan['janelas'])} janelas, pesos {plan['pesos']}, "
              f"tokens não representados = {plan['tokens_nao_representados']}")
        for number, (start, end) in enumerate(plan["janelas"], start=1):
            print(f"   janela {number}: tokens [{start}, {end}) | começa em \"{tokenizer.decode(ids[start:start + 6])}…\" | "
                  f"termina em \"…{tokenizer.decode(ids[max(start, end - 6):end])}\"")
        print(f"   fim do texto original: \"…{' '.join(example['texto'].split()[-6:])}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
