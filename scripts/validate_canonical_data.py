#!/usr/bin/env python3
"""Validação estrutural dos CSVs canônicos do FiscalGraph BR.

Não valida dígitos verificadores do CNPJ. Não imprime dados pessoais.
"""
from __future__ import annotations
import argparse
import csv
import re
import sys
from pathlib import Path

SCHEMAS = {
    "fontes.csv": ["fonte_id", "nome", "orgao_responsavel", "url", "data_coleta", "competencia", "arquivo_origem"],
    "empresas.csv": ["cnpj_basico", "razao_social", "natureza_juridica", "porte", "capital_social", "fonte_id", "registro_origem"],
    "estabelecimentos.csv": ["cnpj", "cnpj_basico", "nome_fantasia", "situacao_cadastral", "data_inicio_atividade", "uf", "municipio", "fonte_id", "registro_origem"],
    "cnaes.csv": ["codigo", "descricao", "fonte_id", "registro_origem"],
    "estabelecimento_cnaes.csv": ["cnpj", "codigo", "principal", "fonte_id", "registro_origem"],
    "socios.csv": ["socio_id", "cnpj_basico", "nome", "tipo_pessoa", "qualificacao", "data_entrada", "fonte_id", "registro_origem"],
    "compliance.csv": ["registro_id", "tipo_registro", "orgao_responsavel", "numero_processo", "data_inicio", "data_fim", "situacao", "descricao", "observacoes", "fundamentacao_legal", "cnpj_sancionado", "fonte_id", "url_fonte", "registro_origem"],
}
CNPJ14 = re.compile(r"^[A-Z0-9]{12}[0-9]{2}$")
BASICO8 = re.compile(r"^[A-Z0-9]{8}$")
KEY_FIELDS = {
    "fontes.csv": ("fonte_id",), "empresas.csv": ("cnpj_basico",),
    "estabelecimentos.csv": ("cnpj",), "cnaes.csv": ("codigo",),
    "estabelecimento_cnaes.csv": ("cnpj", "codigo"),
    "socios.csv": ("socio_id",), "compliance.csv": ("registro_id",),
}


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def validate_file(path: Path, expected: list[str]) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"Arquivo ausente: {path}"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != expected:
                return [f"Cabeçalho incompatível em {path.name}: esperado {expected}; recebido {reader.fieldnames}"]
            rows = list(reader)
    except UnicodeDecodeError:
        return [f"Encoding inválido em {path.name}; salve em UTF-8."]
    if not rows:
        errors.append(f"AVISO: {path.name} tem cabeçalho, mas nenhuma linha de dados.")
    key_fields = KEY_FIELDS.get(path.name, ())
    seen_keys = set()
    for line, row in enumerate(rows, start=2):
        key_value = tuple((row.get(field) or "").strip() for field in key_fields)
        if key_fields and any(not value for value in key_value):
            errors.append(f"{path.name}:{line}: identificador obrigatório ({', '.join(key_fields)}) incompleto.")
        if key_fields and all(key_value):
            if key_value in seen_keys:
                errors.append(f"{path.name}:{line}: chave duplicada em ({', '.join(key_fields)}).")
            seen_keys.add(key_value)
        if path.name == "empresas.csv":
            value = normalize_identifier(row.get("cnpj_basico", ""))
            if value and not BASICO8.fullmatch(value):
                errors.append(f"{path.name}:{line}: cnpj_basico não tem 8 caracteres alfanuméricos.")
        if path.name in ("estabelecimentos.csv", "estabelecimento_cnaes.csv"):
            value = normalize_identifier(row.get("cnpj", ""))
            if value and not CNPJ14.fullmatch(value):
                errors.append(f"{path.name}:{line}: CNPJ não tem formato estrutural de 14 caracteres (12 alfanuméricos + 2 numéricos).")
        if path.name == "estabelecimentos.csv":
            cnpj = normalize_identifier(row.get("cnpj", ""))
            basico = normalize_identifier(row.get("cnpj_basico", ""))
            if cnpj and basico and cnpj[:8] != basico:
                errors.append(f"{path.name}:{line}: cnpj_basico não corresponde aos 8 primeiros caracteres do CNPJ.")
        if path.name == "compliance.csv":
            cnpj = normalize_identifier(row.get("cnpj_sancionado", ""))
            if cnpj and not CNPJ14.fullmatch(cnpj):
                errors.append(f"{path.name}:{line}: cnpj_sancionado não tem formato estrutural de 14 caracteres.")
        if path.name == "socios.csv":
            # Detecta colunas extras/valores no campo destinado a CPF sem exibir o valor.
            if any("cpf" in (key or "").lower() for key in row.keys()):
                errors.append(f"{path.name}:{line}: não inclua coluna de CPF bruto no contrato canônico.")
    print(f"{path.name}: {len(rows)} linha(s) lida(s)")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("data/processed/canonical"))
    args = parser.parse_args()
    issues: list[str] = []
    for filename, schema in SCHEMAS.items():
        issues.extend(validate_file(args.directory / filename, schema))
    errors = [item for item in issues if not item.startswith("AVISO:")]
    for item in issues:
        print(item, file=sys.stderr if item in errors else sys.stdout)
    if errors:
        print(f"Validação terminou com {len(errors)} erro(s).")
        return 1
    print("Validação estrutural concluída. Revise os avisos e a qualidade semântica manualmente.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
