#!/usr/bin/env python3
"""Valida referências entre os sete CSVs canônicos do FiscalGraph BR.

Não valida dígitos verificadores de CNPJ e não infere identidade por nomes.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

FILES = (
    "fontes.csv",
    "empresas.csv",
    "estabelecimentos.csv",
    "cnaes.csv",
    "estabelecimento_cnaes.csv",
    "socios.csv",
    "compliance.csv",
)
CNPJ14 = re.compile(r"^[A-Z0-9]{12}[0-9]{2}$")
BASICO8 = re.compile(r"^[A-Z0-9]{8}$")


def read_rows(directory: Path) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for filename in FILES:
        path = directory / filename
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo ausente: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            result[filename] = list(csv.DictReader(handle))
    return result


def norm(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def duplicate_count(rows: list[dict[str, str]], key: str) -> int:
    values = [(row.get(key) or "").strip() for row in rows]
    return len(values) - len(set(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory", type=Path, default=Path("data/processed/canonical")
    )
    args = parser.parse_args()

    try:
        tables = read_rows(args.directory)
    except (OSError, UnicodeError) as exc:
        print(f"ERRO: {exc}")
        return 1

    fontes = tables["fontes.csv"]
    empresas = tables["empresas.csv"]
    estabelecimentos = tables["estabelecimentos.csv"]
    cnaes = tables["cnaes.csv"]
    estab_cnaes = tables["estabelecimento_cnaes.csv"]
    socios = tables["socios.csv"]
    compliance = tables["compliance.csv"]

    source_ids = {(r.get("fonte_id") or "").strip() for r in fontes}
    company_ids = {(r.get("cnpj_basico") or "").strip() for r in empresas}
    establishment_ids = {(r.get("cnpj") or "").strip() for r in estabelecimentos}
    cnae_ids = {(r.get("codigo") or "").strip() for r in cnaes}

    errors: list[str] = []
    warnings: list[str] = []

    key_specs = (
        ("fontes.csv", fontes, "fonte_id"),
        ("empresas.csv", empresas, "cnpj_basico"),
        ("estabelecimentos.csv", estabelecimentos, "cnpj"),
        ("cnaes.csv", cnaes, "codigo"),
        ("socios.csv", socios, "socio_id"),
        ("compliance.csv", compliance, "registro_id"),
    )
    for filename, rows, key in key_specs:
        blanks = sum(1 for r in rows if not (r.get(key) or "").strip())
        duplicates = duplicate_count(rows, key)
        if blanks:
            errors.append(f"{filename}: {blanks} chave(s) vazia(s) em {key}.")
        if duplicates:
            errors.append(f"{filename}: {duplicates} chave(s) duplicada(s) em {key}.")

    for row_number, row in enumerate(empresas, start=2):
        basic = norm(row.get("cnpj_basico"))
        if not BASICO8.fullmatch(basic):
            errors.append(f"empresas.csv:{row_number}: cnpj_basico fora do formato estrutural.")
        if row.get("fonte_id") not in source_ids:
            errors.append(f"empresas.csv:{row_number}: fonte_id sem correspondência em fontes.csv.")

    for row_number, row in enumerate(estabelecimentos, start=2):
        cnpj = norm(row.get("cnpj"))
        basic = norm(row.get("cnpj_basico"))
        if not CNPJ14.fullmatch(cnpj):
            errors.append(f"estabelecimentos.csv:{row_number}: CNPJ fora do formato estrutural.")
        if cnpj[:8] != basic:
            errors.append(f"estabelecimentos.csv:{row_number}: cnpj_basico difere dos 8 primeiros caracteres.")
        if row.get("cnpj_basico") not in company_ids:
            errors.append(f"estabelecimentos.csv:{row_number}: empresa referenciada não existe.")
        if row.get("fonte_id") not in source_ids:
            errors.append(f"estabelecimentos.csv:{row_number}: fonte_id sem correspondência.")

    for row_number, row in enumerate(socios, start=2):
        if row.get("cnpj_basico") not in company_ids:
            errors.append(f"socios.csv:{row_number}: empresa referenciada não existe.")
        if row.get("fonte_id") not in source_ids:
            errors.append(f"socios.csv:{row_number}: fonte_id sem correspondência.")

    for row_number, row in enumerate(cnaes, start=2):
        if row.get("fonte_id") not in source_ids:
            errors.append(f"cnaes.csv:{row_number}: fonte_id sem correspondência.")

    pairs: set[tuple[str, str]] = set()
    for row_number, row in enumerate(estab_cnaes, start=2):
        pair = ((row.get("cnpj") or "").strip(), (row.get("codigo") or "").strip())
        if pair in pairs:
            errors.append(f"estabelecimento_cnaes.csv:{row_number}: associação CNPJ/CNAE duplicada.")
        pairs.add(pair)
        if pair[0] not in establishment_ids:
            errors.append(f"estabelecimento_cnaes.csv:{row_number}: estabelecimento não existe.")
        if pair[1] not in cnae_ids:
            errors.append(f"estabelecimento_cnaes.csv:{row_number}: CNAE não existe.")
        if row.get("fonte_id") not in source_ids:
            errors.append(f"estabelecimento_cnaes.csv:{row_number}: fonte_id sem correspondência.")
        if (row.get("principal") or "").strip().lower() not in {"true", "false", "1", "0", "sim", "não", "nao"}:
            errors.append(f"estabelecimento_cnaes.csv:{row_number}: valor de principal não reconhecido.")

    for row_number, row in enumerate(compliance, start=2):
        cnpj = norm(row.get("cnpj_sancionado"))
        if not CNPJ14.fullmatch(cnpj):
            errors.append(f"compliance.csv:{row_number}: cnpj_sancionado fora do formato estrutural.")
        if cnpj not in establishment_ids:
            errors.append(f"compliance.csv:{row_number}: CNPJ sancionado sem estabelecimento correspondente.")
        if row.get("fonte_id") not in source_ids:
            errors.append(f"compliance.csv:{row_number}: fonte_id sem correspondência.")

    print("Contagem de linhas:")
    for filename in FILES:
        print(f"  {filename}: {len(tables[filename])}")

    if errors:
        print(f"\nFALHA: {len(errors)} problema(s) encontrado(s):")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nSUCESSO: chaves e referências entre os sete arquivos estão consistentes.")
    if warnings:
        print("Avisos:")
        for warning in warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
