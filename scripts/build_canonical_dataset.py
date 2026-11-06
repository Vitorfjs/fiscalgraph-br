#!/usr/bin/env python3
"""Geração dos CSVs canônicos do FiscalGraph BR para Dev2.

Combina os registros reais do CEIS e CNEP baixados em data/raw/
com os dados cadastrais oficiais do CNPJ (dados públicos cadastrais da RFB, consultados por meio
do serviço intermediário de terceiros Minha Receita.).
Preserva CNPJ como string, normaliza datas para YYYY-MM-DD e cria hashes
técnicos de sócios sem expor CPF.
"""

from __future__ import annotations
import csv
import hashlib
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed/canonical")

CEIS_FILE = RAW_DIR / "20261105_CEIS.csv"
CNEP_FILE = RAW_DIR / "20261105_CNEP.csv"

def parse_date(date_str: str) -> str:
    date_str = (date_str or "").strip().strip("'\"")
    if not date_str or date_str.lower() in ("sem informação", "sem informacao", "null", "none"):
        return ""
    # Try DD/MM/YYYY
    match = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    # Try YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str
    return ""

def clean_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip().strip("'\"")
    if cleaned.lower() in ("sem informação", "sem informacao", "null", "none"):
        return ""
    # Remove excessive newlines or semicolons
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned).strip()
    return cleaned

def generate_socio_id(cnpj_basico: str, nome: str, index: int) -> str:
    seed = f"{cnpj_basico}:{index}:{nome.strip().upper()}".encode("utf-8")
    return "SOC-" + hashlib.sha256(seed).hexdigest()[:12].upper()

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("1. Lendo registros do CEIS e CNEP em data/raw/...")
    
    ceis_records_by_cnpj: dict[str, list[dict]] = {}
    with CEIS_FILE.open("r", encoding="latin-1") as f:
        reader = csv.DictReader(f, delimiter=";")
        for line_num, row in enumerate(reader, start=2):
            tipo_pessoa = (row.get("TIPO DE PESSOA") or "").strip().upper()
            if tipo_pessoa != "J":
                continue
            doc = re.sub(r"[^A-Za-z0-9]", "", row.get("CPF OU CNPJ DO SANCIONADO", "").upper())
            if len(doc) != 14:
                continue
            
            sancao_id = clean_text(row.get("CÓDIGO DA SANÇÃO", ""))
            reg_id = f"CEIS-{sancao_id}" if sancao_id else f"CEIS-L{line_num}"
            
            rec = {
                "registro_id": reg_id,
                "tipo_registro": "CEIS",
                "orgao_responsavel": clean_text(row.get("ÓRGÃO SANCIONADOR", "")),
                "numero_processo": clean_text(row.get("NÚMERO DO PROCESSO", "")),
                "data_inicio": parse_date(row.get("DATA INÍCIO SANÇÃO", "")),
                "data_fim": parse_date(row.get("DATA FINAL SANÇÃO", "")),
                "situacao": clean_text(row.get("ABRAGÊNCIA DA SANÇÃO", "")),
                "descricao": clean_text(row.get("CATEGORIA DA SANÇÃO", "")),
                "observacoes": clean_text(row.get("OBSERVAÇÕES", "")),
                "fundamentacao_legal": clean_text(row.get("FUNDAMENTAÇÃO LEGAL", "")),
                "cnpj_sancionado": doc,
                "fonte_id": "F-CGU-CEIS",
                "url_fonte": "https://portaldatransparencia.gov.br/download-de-dados/ceis",
                "registro_origem": f"20261105_CEIS.csv:L{line_num}"
            }
            ceis_records_by_cnpj.setdefault(doc, []).append(rec)
            
    print(f"   CEIS: {len(ceis_records_by_cnpj)} CNPJs PJ únicos encontrados.")

    cnep_records_by_cnpj: dict[str, list[dict]] = {}
    with CNEP_FILE.open("r", encoding="latin-1") as f:
        reader = csv.DictReader(f, delimiter=";")
        for line_num, row in enumerate(reader, start=2):
            tipo_pessoa = (row.get("TIPO DE PESSOA") or "").strip().upper()
            if tipo_pessoa != "J":
                continue
            doc = re.sub(r"[^A-Za-z0-9]", "", row.get("CPF OU CNPJ DO SANCIONADO", "").upper())
            if len(doc) != 14:
                continue
            
            sancao_id = clean_text(row.get("CÓDIGO DA SANÇÃO", ""))
            reg_id = f"CNEP-{sancao_id}" if sancao_id else f"CNEP-L{line_num}"
            
            rec = {
                "registro_id": reg_id,
                "tipo_registro": "CNEP",
                "orgao_responsavel": clean_text(row.get("ÓRGÃO SANCIONADOR", "")),
                "numero_processo": clean_text(row.get("NÚMERO DO PROCESSO", "")),
                "data_inicio": parse_date(row.get("DATA INÍCIO SANÇÃO", "")),
                "data_fim": parse_date(row.get("DATA FINAL SANÇÃO", "")),
                "situacao": clean_text(row.get("ABRAGÊNCIA DA SANÇÃO", "")),
                "descricao": clean_text(row.get("CATEGORIA DA SANÇÃO", "")),
                "observacoes": clean_text(row.get("OBSERVAÇÕES", "")),
                "fundamentacao_legal": clean_text(row.get("FUNDAMENTAÇÃO LEGAL", "")),
                "cnpj_sancionado": doc,
                "fonte_id": "F-CGU-CNEP",
                "url_fonte": "https://portaldatransparencia.gov.br/download-de-dados/cnep",
                "registro_origem": f"20261105_CNEP.csv:L{line_num}"
            }
            cnep_records_by_cnpj.setdefault(doc, []).append(rec)

    print(f"   CNEP: {len(cnep_records_by_cnpj)} CNPJs PJ únicos encontrados.")

    both_cnpjs = sorted(list(set(ceis_records_by_cnpj.keys()).intersection(set(cnep_records_by_cnpj.keys()))))
    ceis_only = sorted(list(set(ceis_records_by_cnpj.keys()) - set(cnep_records_by_cnpj.keys())))
    cnep_only = sorted(list(set(cnep_records_by_cnpj.keys()) - set(ceis_records_by_cnpj.keys())))
    
    print(f"   Interseção (em ambos): {len(both_cnpjs)}")
    
    # Seleção de recorte enxuto de 18 empresas:
    # 10 de interseção, 4 apenas CEIS, 4 apenas CNEP
    selected_cnpjs = both_cnpjs[:10] + ceis_only[:4] + cnep_only[:4]
    print(f"2. Recorte selecionado: {len(selected_cnpjs)} empresas representativas.")
    
    empresas_rows = []
    estabelecimentos_rows = []
    cnaes_dict: dict[str, str] = {}
    estab_cnaes_rows = []
    socios_rows = []
    compliance_rows = []
    
    print("3. Coletando dados cadastrais oficiais e montando tabelas canônicas...")
    skipped_cnpjs = []
    for idx, cnpj in enumerate(selected_cnpjs, start=1):
        cnpj_str = str(cnpj).zfill(14)
        cnpj_basico = cnpj_str[:8]
        
        # Obter dados cadastrais da Receita Federal
        url = f"https://minhareceita.org/{cnpj_str}"
        data = None
        for attempt in range(3):
            try:
                time.sleep(1.8)
                req = urllib.request.Request(url, headers={"User-Agent": "FiscalGraphBR/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    break
            except Exception as e:
                print(f"   Aviso: tentativa {attempt+1} para {cnpj_str} falhou ({e}). Aguardando...")
                time.sleep(3)
                
        if not data:
            skipped_cnpjs.append({
                "cnpj": cnpj_str,
                "motivo": "API de consulta cadastral não retornou dados após as tentativas"
            })
            continue
            
        razao = clean_text(data.get("razao_social", ""))
        natureza = clean_text(data.get("natureza_juridica", ""))
        porte = clean_text(data.get("porte", ""))
        capital = str(data.get("capital_social", "") or "")
        
        # empresas.csv
        empresas_rows.append({
            "cnpj_basico": cnpj_basico,
            "razao_social": razao,
            "natureza_juridica": natureza,
            "porte": porte,
            "capital_social": capital,
            "fonte_id": "F-RFB-CNPJ",
            "registro_origem": f"ReceitaFederal:CNPJ:{cnpj_str}"
        })
        
        # estabelecimentos.csv
        nome_fantasia = clean_text(data.get("nome_fantasia", ""))
        situacao_cadastral = clean_text(str(data.get("descricao_situacao_cadastral", "") or data.get("situacao_cadastral", "")))
        data_inicio = parse_date(data.get("data_inicio_atividade", ""))
        uf = clean_text(data.get("uf", ""))
        municipio = clean_text(data.get("municipio", ""))
        
        estabelecimentos_rows.append({
            "cnpj": cnpj_str,
            "cnpj_basico": cnpj_basico,
            "nome_fantasia": nome_fantasia,
            "situacao_cadastral": situacao_cadastral,
            "data_inicio_atividade": data_inicio,
            "uf": uf,
            "municipio": municipio,
            "fonte_id": "F-RFB-CNPJ",
            "registro_origem": f"ReceitaFederal:Estabelecimento:{cnpj_str}"
        })
        
        # CNAE fiscal principal
        cnae_fiscal = str(data.get("cnae_fiscal", "") or "").strip()
        cnae_desc = clean_text(data.get("cnae_fiscal_descricao", ""))
        if cnae_fiscal:
            cnaes_dict[cnae_fiscal] = cnae_desc
            estab_cnaes_rows.append({
                "cnpj": cnpj_str,
                "codigo": cnae_fiscal,
                "principal": "True",
                "fonte_id": "F-RFB-CNPJ",
                "registro_origem": f"ReceitaFederal:CNAE:{cnpj_str}"
            })
            
        # CNAEs secundários (amostra de até 2 por estabelecimento para manter enxuto)
        for sec in data.get("cnaes_secundarios", [])[:2]:
            sec_cod = str(sec.get("codigo", "") or "").strip()
            sec_desc = clean_text(sec.get("descricao", ""))
            if sec_cod:
                cnaes_dict[sec_cod] = sec_desc
                estab_cnaes_rows.append({
                    "cnpj": cnpj_str,
                    "codigo": sec_cod,
                    "principal": "False",
                    "fonte_id": "F-RFB-CNPJ",
                    "registro_origem": f"ReceitaFederal:CNAESec:{cnpj_str}"
                })
                
        # Sócios (QSA)
        for s_idx, socio in enumerate(data.get("qsa", []), start=1):
            s_nome = clean_text(socio.get("nome_socio", ""))
            s_qualif = clean_text(socio.get("qualificacao_socio", ""))
            s_data_ent = parse_date(socio.get("data_entrada_sociedade", ""))
            try:
                identificador_socio = int(socio.get("identificador_de_socio") or 0)
            except (TypeError, ValueError):
                identificador_socio = -1

            s_tipo = "PESSOA FISICA" if identificador_socio == 2 else "PESSOA JURIDICA"
            
            socio_id = generate_socio_id(cnpj_basico, s_nome, s_idx)
            socios_rows.append({
                "socio_id": socio_id,
                "cnpj_basico": cnpj_basico,
                "nome": s_nome,
                "tipo_pessoa": s_tipo,
                "qualificacao": s_qualif,
                "data_entrada": s_data_ent,
                "fonte_id": "F-RFB-CNPJ",
                "registro_origem": f"ReceitaFederal:QSA:{cnpj_str}:S{s_idx}"
            })
            
        # Compliance (CEIS e CNEP) associados a esta empresa
        for rec in ceis_records_by_cnpj.get(cnpj_str, []):
            compliance_rows.append(rec)
        for rec in cnep_records_by_cnpj.get(cnpj_str, []):
            compliance_rows.append(rec)
            
        print(f"   [{idx}/{len(selected_cnpjs)}] Processado: {cnpj_str} ({razao})")
        
    # cnaes.csv
    cnaes_rows = [
        {
            "codigo": cod,
            "descricao": desc,
            "fonte_id": "F-IBGE-CNAE",
            "registro_origem": f"IBGE:CONCLA:{cod}"
        }
        for cod, desc in sorted(cnaes_dict.items())
    ]
    
    # fontes.csv
    fontes_rows = [
        {
            "fonte_id": "F-CGU-CEIS",
            "nome": "Cadastro de Empresas Inidôneas e Suspensas",
            "orgao_responsavel": "Controladoria-Geral da União (CGU)",
            "url": "https://portaldatransparencia.gov.br/download-de-dados/ceis",
            "data_coleta": "2026-11-05T10:34:00-03:00",
            "competencia": "2026-11-04",
            "arquivo_origem": "20261105_CEIS.csv"
        },
        {
            "fonte_id": "F-CGU-CNEP",
            "nome": "Cadastro Nacional de Empresas Punidas",
            "orgao_responsavel": "Controladoria-Geral da União (CGU)",
            "url": "https://portaldatransparencia.gov.br/download-de-dados/cnep",
            "data_coleta": "2026-11-05T10:34:00-03:00",
            "competencia": "2026-11-04",
            "arquivo_origem": "20261105_CNEP.csv"
        },
        {
            "fonte_id": "F-RFB-CNPJ",
            "nome": "Cadastro Nacional da Pessoa Jurídica",
            "orgao_responsavel": "Secretaria Especial da Receita Federal do Brasil",
            "url": "https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj",
            "data_coleta": "2026-11-05T10:44:00-03:00",
            "competencia": "2026-11-04",
            "arquivo_origem": "Receita Federal (Espelho de Dados Abertos)"
        },
        {
            "fonte_id": "F-IBGE-CNAE",
            "nome": "Classificação Nacional de Atividades Econômicas",
            "orgao_responsavel": "Instituto Brasileiro de Geografia e Estatística (IBGE)",
            "url": "https://concla.ibge.gov.br",
            "data_coleta": "2026-11-05T10:44:00-03:00",
            "competencia": "2026-11-04",
            "arquivo_origem": "Retorno JSON (API Minha Receita)",
        }
    ]
    
    # Salvar todos os 7 arquivos canônicos
    print("4. Gravando arquivos canônicos em data/processed/canonical/...")
    
    def write_canonical(filename: str, fieldnames: list[str], rows: list[dict]):
        path = OUT_DIR / filename
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        print(f"   {filename}: {len(rows)} linhas gravadas.")

    write_canonical("fontes.csv", ["fonte_id", "nome", "orgao_responsavel", "url", "data_coleta", "competencia", "arquivo_origem"], fontes_rows)
    write_canonical("empresas.csv", ["cnpj_basico", "razao_social", "natureza_juridica", "porte", "capital_social", "fonte_id", "registro_origem"], empresas_rows)
    write_canonical("estabelecimentos.csv", ["cnpj", "cnpj_basico", "nome_fantasia", "situacao_cadastral", "data_inicio_atividade", "uf", "municipio", "fonte_id", "registro_origem"], estabelecimentos_rows)
    write_canonical("cnaes.csv", ["codigo", "descricao", "fonte_id", "registro_origem"], cnaes_rows)
    write_canonical("estabelecimento_cnaes.csv", ["cnpj", "codigo", "principal", "fonte_id", "registro_origem"], estab_cnaes_rows)
    write_canonical("socios.csv", ["socio_id", "cnpj_basico", "nome", "tipo_pessoa", "qualificacao", "data_entrada", "fonte_id", "registro_origem"], socios_rows)
    write_canonical("compliance.csv", ["registro_id", "tipo_registro", "orgao_responsavel", "numero_processo", "data_inicio", "data_fim", "situacao", "descricao", "observacoes", "fundamentacao_legal", "cnpj_sancionado", "fonte_id", "url_fonte", "registro_origem"], compliance_rows)
    
    print("Processamento concluído com sucesso!")
    
    build_report = {
        "execucao_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cnpjs_planejados": len(selected_cnpjs),
        "empresas_geradas": len(empresas_rows),
        "cnpjs_sem_resposta_cadastral": skipped_cnpjs,
        "execucao_parcial": bool(skipped_cnpjs),
        "arquivos_gerados": [
            "fontes.csv", "empresas.csv", "estabelecimentos.csv",
            "cnaes.csv", "estabelecimento_cnaes.csv", "socios.csv", "compliance.csv"
        ]
    }
    (OUT_DIR / "build_report.json").write_text(
        json.dumps(build_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"Empresas geradas: {len(empresas_rows)} de {len(selected_cnpjs)} selecionadas.")
    print(f"Consultas cadastrais sem retorno: {len(skipped_cnpjs)}.")
    if skipped_cnpjs:
        print("ATENÇÃO: amostra parcial. Consulte build_report.json.")

if __name__ == "__main__":
    main()

