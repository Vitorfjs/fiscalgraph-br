#!/usr/bin/env python3
"""Extrator Text-to-Graph para registros de compliance (CEIS/CNEP).

Etapas:
- Trecho: concatena os campos textuais do registro em uma unidade rastreável.
- Privacidade: CPF formatado presente no texto é mascarado antes da extração.
- CNPJ: regex estrutural (numérico ou alfanumérico), sem cálculo de dígitos verificadores.
- Organizações: spaCy ``pt_core_news_sm`` quando ``--with-spacy`` for informado.
- Relação extraída: MENCIONA com status CANDIDATA; não representa vínculo jurídico.

Uso:
    python pipeline/text_to_graph/extractor.py --input data/processed/canonical/compliance.csv \
        --output data/processed/trechos.jsonl --with-spacy
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

# Campos textuais do contrato canônico, na ordem em que compõem o trecho.
TEXT_FIELDS: tuple[tuple[str, str], ...] = (
    ("descricao", "Descrição"),
    ("observacoes", "Observações"),
    ("fundamentacao_legal", "Fundamentação legal"),
)
REQUIRED_COLUMNS = {"registro_id", "fonte_id", "descricao", "observacoes", "fundamentacao_legal"}
SEPARATOR = "\n"

# CNPJ formatado (XX.XXX.XXX/XXXX-XX) ou contínuo (14 posições).
# As 12 primeiras posições aceitam letras maiúsculas e dígitos (CNPJ alfanumérico, RFB 2026);
# as 2 últimas são sempre dígitos. Não usa IGNORECASE: o formato oficial é em maiúsculas.
CNPJ_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[A-Z0-9]{2}\.[A-Z0-9]{3}\.[A-Z0-9]{3}/[A-Z0-9]{4}-[0-9]{2}"
    r"|[A-Z0-9]{12}[0-9]{2})"
    r"(?![A-Za-z0-9])"
)
# CPF formatado é mascarado; CPF não deve sair do pipeline.
CPF_RE = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
CPF_MASK = "[CPF REMOVIDO]"

# Entidades ORG muito curtas ou sem letras são ruído típico em texto administrativo.
MIN_ORG_LENGTH = 3
# Linhas com mais desta proporção de letras maiúsculas são transcrições de lei
# (ex.: fundamentacao_legal). O modelo pt_core_news_sm marca quase toda palavra em
# CAIXA ALTA como ORG nesse tipo de texto, então entidades nessas linhas são descartadas.
UPPERCASE_LINE_RATIO = 0.8
# Termos administrativos genéricos que o NER costuma marcar como ORG sem serem organizações.
ORG_STOPLIST = {
    "dou", "d.o.u", "cnpj", "cpf", "decisão", "decisao", "processo", "recurso administrativo",
    "administração pública", "administracao publica", "lei", "art", "inciso",
}

METODO_CNPJ = "regex_cnpj_estrutural"
METODO_ORG = "spacy_ner_pt_core_news_sm"


def normalize_cnpj(value: str) -> str:
    """Remove pontuação e converte para maiúsculas, preservando zeros à esquerda."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def normalize_organization_name(value: str) -> str:
    """Normaliza o nome da organização para fins de agrupamento semântico/resolução leve.

    Converte para maiúsculas, remove acentuação, caracteres especiais e sufixos
    empresariais comuns (LTDA, S/A, EIRELI, ME, EPP), preservando o radical empresarial.
    """
    if not value:
        return ""
    # Remove acentos
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    # Remove pontuações e símbolos
    text = re.sub(r"[^\w\s]", " ", text)
    # Remove sufixos jurídicos frequentes
    text = re.sub(r"\b(LTDA|SA|S A|EIRELI|ME|EPP|CIA|COMPANHIA)\b", " ", text)
    return " ".join(text.split())


def structural_cnpj(value: str) -> bool:
    """Valida apenas a estrutura: 14 posições, 12 alfanuméricas + 2 dígitos finais."""
    normalized = normalize_cnpj(value)
    return (
        len(normalized) == 14
        and normalized[:12].isalnum()
        and normalized[:12].isascii()
        and normalized[-2:].isdigit()
    )


def stable_id(*parts: str) -> str:
    """Identificador determinístico: mesmas entradas geram sempre o mesmo id."""
    payload = "|".join(str(p or "") for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def mask_cpf(text: str) -> tuple[str, int]:
    """Mascara CPFs formatados. Retorna o texto e a quantidade de substituições."""
    return CPF_RE.subn(CPF_MASK, text or "")


def _looks_like_cnpj_candidate(raw: str) -> bool:
    """Reduz falsos positivos da forma contínua sem pontuação.

    Uma sequência de 14 letras/dígitos sem nenhum dígito nas 12 primeiras posições
    é quase sempre uma palavra, não um identificador.
    """
    if "." in raw or "/" in raw:
        return True
    return any(ch.isdigit() for ch in raw[:12])


def _uppercase_line_spans(text: str) -> list[tuple[int, int]]:
    """Retorna os intervalos (inicio, fim) das linhas dominadas por maiúsculas."""
    spans: list[tuple[int, int]] = []
    offset = 0
    for line in text.split("\n"):
        letters = [ch for ch in line if ch.isalpha()]
        if letters and sum(ch.isupper() for ch in letters) / len(letters) > UPPERCASE_LINE_RATIO:
            spans.append((offset, offset + len(line)))
        offset += len(line) + 1
    return spans


def _is_valid_org(value: str, start: int, upper_spans: list[tuple[int, int]]) -> bool:
    if len(value) < MIN_ORG_LENGTH or not any(ch.isalpha() for ch in value):
        return False
    if value.lower().strip(" .,;:") in ORG_STOPLIST:
        return False
    return not any(lo <= start < hi for lo, hi in upper_spans)


def extract_mentions(text: str, nlp: Any = None) -> list[dict[str, Any]]:
    """Extrai menções de CNPJ (regex) e, opcionalmente, de organizações (spaCy).

    Toda menção recebe ``status='CANDIDATA'``: é uma ocorrência textual, não um vínculo.
    ``inicio``/``fim`` são offsets de caractere sobre ``text``.
    """
    mentions: list[dict[str, Any]] = []
    for match in CNPJ_RE.finditer(text or ""):
        raw = match.group(0)
        if not _looks_like_cnpj_candidate(raw):
            continue
        normalized = normalize_cnpj(raw)
        if structural_cnpj(normalized):
            mentions.append({
                "tipo": "CNPJ",
                "valor": normalized,
                "inicio": match.start(),
                "fim": match.end(),
                "metodo": METODO_CNPJ,
                "status": "CANDIDATA",
            })
    if nlp is not None and text:
        doc = nlp(text)
        upper_spans = _uppercase_line_spans(text)
        for ent in doc.ents:
            if ent.label_ != "ORG":
                continue
            value = ent.text.strip()
            if not _is_valid_org(value, ent.start_char, upper_spans):
                continue
            mentions.append({
                "tipo": "ORGANIZACAO",
                "valor": value,
                "valor_normalizado": normalize_organization_name(value),
                "inicio": ent.start_char,
                "fim": ent.end_char,
                "metodo": METODO_ORG,
                "status": "CANDIDATA",
            })
    # Remove duplicatas exatas (tipo + span + valor) sem fundir menções diferentes.
    unique: dict[tuple, dict] = {}
    for mention in mentions:
        unique[(mention["tipo"], mention["inicio"], mention["fim"], mention["valor"])] = mention
    return sorted(unique.values(), key=lambda m: (m["inicio"], m["fim"], m["tipo"]))


def compose_text(record: dict[str, str]) -> str:
    """Concatena os campos textuais disponíveis, na ordem do contrato."""
    parts = [(record.get(field) or "").strip() for field, _ in TEXT_FIELDS]
    return SEPARATOR.join(part for part in parts if part)


def build_chunk(record: dict[str, str], nlp: Any = None) -> dict[str, Any] | None:
    """Cria um trecho rastreável a partir de um registro de compliance.

    Retorna ``None`` quando o registro não possui texto.
    """
    text, cpf_masked = mask_cpf(compose_text(record))
    if not text:
        return None
    registro_id = (record.get("registro_id") or "").strip()
    fonte_id = (record.get("fonte_id") or "").strip()
    chunk = {
        "trecho_id": stable_id(registro_id, text),
        "registro_id": registro_id,
        "texto": text,
        "fonte_id": fonte_id,
        "url_fonte": (record.get("url_fonte") or "").strip(),
        "registro_origem": (record.get("registro_origem") or "").strip(),
        "metodo_extracao": "regex_cnpj" + ("+spacy_ner" if nlp is not None else ""),
        "mencoes": extract_mentions(text, nlp),
    }
    if cpf_masked:
        chunk["cpf_mascarados"] = cpf_masked
    return chunk


def load_nlp(enabled: bool):
    """Carrega o modelo spaCy em português, com mensagem clara se estiver ausente."""
    if not enabled:
        return None
    try:
        import spacy
    except ImportError as exc:
        raise RuntimeError("spaCy não está instalado. Execute: pip install -r requirements-dev4.txt") from exc
    try:
        return spacy.load("pt_core_news_sm")
    except OSError as exc:
        raise RuntimeError("Modelo ausente. Execute: python -m spacy download pt_core_news_sm") from exc


def process_csv(input_path: Path, output_path: Path, with_spacy: bool = False, nlp: Any = None) -> dict[str, Any]:
    """Lê o CSV canônico de compliance e grava um trecho JSON por linha.

    Retorna estatísticas da execução (usadas no relatório e na documentação).
    """
    if nlp is None:
        nlp = load_nlp(with_spacy)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stats: dict[str, Any] = {
        "entrada": str(input_path),
        "saida": str(output_path),
        "spacy": nlp is not None,
        "registros_lidos": 0,
        "registros_sem_texto": 0,
        "trechos_gerados": 0,
        "trechos_duplicados": 0,
        "cpf_mascarados": 0,
        "mencoes_total": 0,
        "mencoes_por_tipo": Counter(),
        "cnpjs_distintos": set(),
        "cnpjs_iguais_ao_sancionado": 0,
    }
    seen_ids: set[str] = set()
    with input_path.open("r", encoding="utf-8-sig", newline="") as source, \
            output_path.open("w", encoding="utf-8", newline="\n") as target:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV sem colunas esperadas: {sorted(missing)}")
        for row in reader:
            stats["registros_lidos"] += 1
            chunk = build_chunk(row, nlp)
            if chunk is None:
                stats["registros_sem_texto"] += 1
                continue
            if chunk["trecho_id"] in seen_ids:
                stats["trechos_duplicados"] += 1
                continue
            seen_ids.add(chunk["trecho_id"])
            target.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            stats["trechos_gerados"] += 1
            stats["cpf_mascarados"] += chunk.get("cpf_mascarados", 0)
            sancionado = normalize_cnpj(row.get("cnpj_sancionado") or "")
            for mention in chunk["mencoes"]:
                stats["mencoes_total"] += 1
                stats["mencoes_por_tipo"][mention["tipo"]] += 1
                if mention["tipo"] == "CNPJ":
                    stats["cnpjs_distintos"].add(mention["valor"])
                    if sancionado and mention["valor"] == sancionado:
                        stats["cnpjs_iguais_ao_sancionado"] += 1
    stats["mencoes_por_tipo"] = dict(stats["mencoes_por_tipo"])
    stats["cnpjs_distintos"] = len(stats["cnpjs_distintos"])
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera trechos e menções candidatas a partir de compliance.csv")
    parser.add_argument("--input", type=Path, required=True, help="CSV canônico de compliance")
    parser.add_argument("--output", type=Path, required=True, help="Arquivo JSONL de saída")
    parser.add_argument("--with-spacy", action="store_true", help="Ativa NER de organizações (pt_core_news_sm)")
    parser.add_argument("--stats", type=Path, help="Opcional: grava as estatísticas em JSON")
    args = parser.parse_args(argv)

    try:
        stats = process_csv(args.input, args.output, args.with_spacy)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print(f"Registros lidos: {stats['registros_lidos']}")
    print(f"Registros sem texto: {stats['registros_sem_texto']}")
    print(f"Trechos gerados: {stats['trechos_gerados']} (duplicados ignorados: {stats['trechos_duplicados']})")
    print(f"Menções extraídas: {stats['mencoes_total']} {stats['mencoes_por_tipo']}")
    print(f"CNPJs distintos mencionados: {stats['cnpjs_distintos']}")
    print(f"CPFs mascarados no texto: {stats['cpf_mascarados']}")
    print(f"NER spaCy: {'ativo' if stats['spacy'] else 'desativado (somente regex de CNPJ)'}")
    print(f"Saída: {args.output}")
    if args.stats:
        args.stats.parent.mkdir(parents=True, exist_ok=True)
        args.stats.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Estatísticas: {args.stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
