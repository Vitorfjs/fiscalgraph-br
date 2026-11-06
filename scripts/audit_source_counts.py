#!/usr/bin/env python3
"""Audita a distribuição dos registros brutos CEIS/CNEP por tipo de pessoa.

O relatório não presume que todo registro seja PF ou PJ: valores vazios ou
inesperados são contabilizados separadamente. Não imprime CPF/CNPJ.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

DOC_FIELD = "CPF OU CNPJ DO SANCIONADO"
TYPE_FIELD = "TIPO DE PESSOA"
CNPJ_PATTERN = re.compile(r"^[A-Z0-9]{12}[0-9]{2}$")


def audit_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    by_type: Counter[str] = Counter()
    valid_identifier_rows = 0
    unique_identifiers: set[str] = set()
    pj_valid_identifier_rows = 0
    pj_unique_identifiers: set[str] = set()
    invalid_or_missing_identifier_rows = 0

    with path.open("r", encoding="latin-1", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        headers = set(reader.fieldnames or [])
        missing = {TYPE_FIELD, DOC_FIELD} - headers
        if missing:
            raise ValueError(
                f"{path.name}: coluna(s) ausente(s): {', '.join(sorted(missing))}. "
                f"Cabeçalhos encontrados: {reader.fieldnames}"
            )

        total = 0
        for row in reader:
            total += 1
            raw_type = (row.get(TYPE_FIELD) or "").strip().upper()
            category = raw_type if raw_type else "VAZIO"
            by_type[category] += 1

            identifier = re.sub(
                r"[^A-Z0-9]", "", (row.get(DOC_FIELD) or "").upper()
            )
            if CNPJ_PATTERN.fullmatch(identifier):
                valid_identifier_rows += 1
                unique_identifiers.add(identifier)
                if category == "J":
                    pj_valid_identifier_rows += 1
                    pj_unique_identifiers.add(identifier)
            else:
                invalid_or_missing_identifier_rows += 1

    return {
        "arquivo": path.name,
        "total_registros": total,
        "distribuicao_tipo_pessoa": dict(sorted(by_type.items())),
        "registros_com_cnpj_em_formato_estrutural": valid_identifier_rows,
        "cnpjs_distintos_em_formato_estrutural_qualquer_tipo": len(unique_identifiers),
        "registros_pj_com_cnpj_em_formato_estrutural": pj_valid_identifier_rows,
        "cnpjs_pj_distintos_em_formato_estrutural": len(pj_unique_identifiers),
        "registros_sem_cnpj_em_formato_estrutural": invalid_or_missing_identifier_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audita contagens brutas CEIS/CNEP sem expor identificadores pessoais."
    )
    parser.add_argument("--ceis", type=Path, required=True, help="CSV bruto CEIS")
    parser.add_argument("--cnep", type=Path, required=True, help="CSV bruto CNEP")
    parser.add_argument("--json", type=Path, help="Opcional: caminho para salvar relatório JSON")
    args = parser.parse_args()

    try:
        report = {
            "ceis": audit_file(args.ceis),
            "cnep": audit_file(args.cnep),
        }
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERRO: {exc}")
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Relatório salvo em: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
