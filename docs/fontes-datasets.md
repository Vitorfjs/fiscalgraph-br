# Fontes e Recorte de Dados — FiscalGraph BR (Dev2)

Este documento regista a proveniência, metadados, regras de recorte e correspondência dos dados públicos empresariais e de sanções utilizados no protótipo do FiscalGraph BR.

---

## Páginas Oficiais para Consulta

- **CNPJ / Catálogo de Dados Abertos (dados.gov.br):** https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj
- **Repositório oficial de dados abertos da Receita Federal:** https://www.gov.br/receitafederal/dados
- **Layout e Metadados do CNPJ (Receita Federal):** https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf
- **Regras do CNPJ Alfanumérico (Receita Federal):** https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/acoes-e-programas/programas-e-atividades/cnpj-alfanumerico/cnpj-alfa
- **CEIS / Portal da Transparência (CGU):** https://portaldatransparencia.gov.br/download-de-dados/ceis
- **Dicionário CEIS (Portal da Transparência):** https://portaldatransparencia.gov.br/dicionario-de-dados/ceis
- **CNEP / Portal da Transparência (CGU):** https://portaldatransparencia.gov.br/download-de-dados/cnep
- **Dicionário CNEP (Portal da Transparência):** https://portaldatransparencia.gov.br/dicionario-de-dados/cnep
- **Classificação Nacional de Atividades Económicas (IBGE/CONCLA):** https://concla.ibge.gov.br

---

## Fonte 1 — CNPJ / Receita Federal do Brasil (RFB)

- **Origem Institucional vs. Meio Técnico:**
  A Secretaria Especial da Receita Federal do Brasil (RFB) é a origem institucional primária dos dados públicos cadastrais do CNPJ. O meio técnico de consulta utilizado neste recorte foi o serviço/API de terceiros `https://minhareceita.org/`, que espelha e disponibiliza dados públicos cadastrais da RFB. Trata-se de um serviço intermediário, sujeito a limitações de disponibilidade e sem garantia de SLA do projeto.
- **URL oficial do conjunto:** https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj e repositório oficial https://www.gov.br/receitafederal/dados
- **Página de metadados/layout consultada e versão/data do documento:** Layout oficial PDF versão 2022 (`cnpj-metadados.pdf`) confrontado com as diretrizes do CNPJ Alfanumérico vigentes desde 31/07/2026.
- **A estrutura efetiva do arquivo tem cabeçalho? Se não, como a ordem de campos foi confirmada?**
  Os arquivos brutos compactados de dados abertos da Receita Federal tradicionalmente não possuem cabeçalho. A ordem dos campos foi confrontada com o layout oficial do CNPJ e validada através do serviço/API de terceiros que espelha dados públicos cadastrais da RFB (minhareceita.org).
- **URL do serviço intermediário consultado:** https://minhareceita.org/ (serviço/API de terceiros que espelha dados públicos cadastrais da RFB).
- **Data e hora da consulta:** 05/11/2026 às 10:44:00-03:00.
- **Competência/referência do dataset:** 04/11/2026.
- **Nomes exatos dos arquivos brutos de referência:** `20261105_CEIS.csv` e `20261105_CNEP.csv` (para extração dos CNPJs de PJs sancionadas) + Dados Abertos da RFB obtidos via serviço intermediário.
- **Campos originais utilizados:**
  - `cnpj` / `cnpj_basico`: 14 carateres textuais (12 alfanuméricos + 2 numéricos) e 8 carateres básicos.
  - `razao_social`: Razão social da empresa.
  - `natureza_juridica`: Descrição da natureza jurídica.
  - `porte`: Porte empresarial (ME, EPP, DEMAIS).
  - `capital_social`: Valor declarado de capital social.
  - `nome_fantasia`: Nome de fantasia do estabelecimento.
  - `situacao_cadastral`: Descrição da situação cadastral (ATIVA, BAIXADA, etc.).
  - `data_inicio_atividade`: Data de abertura normalizada em `YYYY-MM-DD`.
  - `uf` e `municipio`: Localização geográfica do estabelecimento.
  - `cnae_fiscal` e `cnae_fiscal_descricao`: Atividade económica principal.
  - `cnaes_secundarios`: Atividades económicas secundárias.
  - `qsa`: Nome dos sócios, qualificação, identificador de tipo (PF/PJ) e data de entrada.
- **Critério de recorte:**
  Seleção determinística ordenada de 18 CNPJs (10 provenientes da interseção CEIS/CNEP, 4 exclusivos do CEIS e 4 exclusivos do CNEP). Conforme registado em `build_report.json`, nesta execução todas as 18 consultas obtiveram retorno cadastral completo (0 consultas sem retorno).
- **Quantidade de linhas canónicas consolidadas:**
  - Base nacional: dezenas de milhões de registos.
  - Recorte canónico gerado: 18 empresas, 18 estabelecimentos, 36 CNAEs, 45 vínculos estabelecimento–CNAE e 26 registos de sócios.
- **Limitações/observações:**
  - Preservado o formato de texto para o CNPJ com zeros à esquerda.
  - Não há exportação de CPF bruto nem dados pessoais não públicos: os identificadores de sócio são sintéticos (`SOC-` + hash de escopo restrito).

---

## Fonte 2 — CEIS (Cadastro de Empresas Inidôneas e Suspensas)

- **URL oficial:** https://portaldatransparencia.gov.br/download-de-dados/ceis
- **Data e hora do download:** 05/11/2026 às 10:34:00-03:00.
- **Competência/data escolhida na página:** 04/11/2026.
- **Nome exato do arquivo e dicionário:**
  - Arquivo: `20261105_CEIS.csv` (tamanho: ~33 MB, codificação Latin-1, delimitador `;`).
  - Dicionário: https://portaldatransparencia.gov.br/dicionario-de-dados/ceis
- **Campos utilizados:**
  - `CADASTRO`: Identificador do cadastro (`CEIS`).
  - `CÓDIGO DA SANÇÃO`: Código numérico estável da sanção.
  - `TIPO DE PESSOA`: Filtro restrito a `J` (Pessoa Jurídica).
  - `CPF OU CNPJ DO SANCIONADO`: CNPJ de 14 dígitos (sem formatação).
  - `ÓRGÃO SANCIONADOR`: Órgão público sancionador.
  - `NÚMERO DO PROCESSO`: Número administrativo/judicial do processo.
  - `CATEGORIA DA SANÇÃO`: Tipo de penalidade (declaração de inidoneidade, suspensão, etc.).
  - `DATA INÍCIO SANÇÃO`: Data de início da vigência da penalidade.
  - `DATA FINAL SANÇÃO`: Data final (quando aplicável).
  - `ABRAGÊNCIA DA SANÇÃO`: Esfera e alcance da sanção.
  - `FUNDAMENTAÇÃO LEGAL`: Artigo de lei / norma que fundamentou a sanção.
  - `OBSERVAÇÕES`: Notas complementares e histórico de publicações.
- **Critério de recorte:**
  - Exclusão rigorosa de pessoas físicas (`TIPO DE PESSOA == "F"`).
  - Filtragem de registos de Pessoa Jurídica com CNPJ válido de 14 posições estruturais.
- **Quantidade de linhas auditadas (arquivo bruto 20261105_CEIS.csv):**
  - Total de registos: 23.765.
  - Distribuição completa de `TIPO DE PESSOA`:
    - `J`: 14.603
    - `F`: 9.151
    - `VAZIO`: 11
  - Registos com CNPJ em formato estrutural: 14.605 (sendo 14.603 do tipo J).
  - CNPJs PJ distintos em formato estrutural: 9.678.
  - Registos sem CNPJ em formato estrutural: 9.160.
  - No recorte canónico consolidado: 38 sanções do CEIS vinculadas às empresas da amostra.
- **Limitações/observações:**
  - Registos de pessoas físicas foram descartados para cumprir as diretrizes de minimização e proteção de dados.
  - Datas nulas ou descritas como "Sem Informação" foram transformadas em cadeias de carateres vazias.

---

## Fonte 3 — CNEP (Cadastro Nacional de Empresas Punidas)

- **URL oficial:** https://portaldatransparencia.gov.br/download-de-dados/cnep
- **Data e hora do download:** 05/11/2026 às 10:34:00-03:00.
- **Competência/data escolhida na página:** 04/11/2026.
- **Nome exato do arquivo e dicionário:**
  - Arquivo: `20261105_CNEP.csv` (tamanho: ~1.8 MB, codificação Latin-1, delimitador `;`).
  - Dicionário: https://portaldatransparencia.gov.br/dicionario-de-dados/cnep
- **Campos utilizados:**
  - `CADASTRO`: Identificador do cadastro (`CNEP`).
  - `CÓDIGO DA SANÇÃO`: Código identificador da sanção.
  - `TIPO DE PESSOA`: Filtro restrito a `J` (Pessoa Jurídica).
  - `CPF OU CNPJ DO SANCIONADO`: CNPJ de 14 dígitos.
  - `ÓRGÃO SANCIONADOR`: Órgão responsável pela aplicação da Lei Anticorrupção.
  - `NÚMERO DO PROCESSO`: Número do processo sancionador.
  - `CATEGORIA DA SANÇÃO`: Modalidade de sanção (multa, publicação extraordinária, etc.).
  - `DATA INÍCIO SANÇÃO` e `DATA FINAL SANÇÃO`: Prazos da penalidade.
  - `ABRAGÊNCIA DA SANÇÃO`: Alcance da punição.
  - `FUNDAMENTAÇÃO LEGAL`: Dispositivos da Lei nº 12.846/2013 (Lei Anticorrupção).
  - `OBSERVAÇÕES`: Detalhes e observações registadas.
- **Critério de recorte:**
  - Apenas Pessoas Jurídicas com identificador CNPJ íntegro.
- **Quantidade de linhas auditadas (arquivo bruto 20261105_CNEP.csv):**
  - Total de registos: 1.854.
  - Distribuição completa de `TIPO DE PESSOA`:
    - `J`: 1.814
    - `F`: 28
    - `VAZIO`: 12
  - Registos com CNPJ em formato estrutural: 1.814 (todos do tipo J).
  - CNPJs PJ distintos em formato estrutural: 1.032.
  - Registos sem CNPJ em formato estrutural: 40 (28 PF + 12 VAZIO).
  - No recorte canónico consolidado: 16 sanções do CNEP vinculadas às empresas da amostra (totalizando 54 sanções no arquivo `compliance.csv`).
- **Limitações/observações:**
  - O CNEP foca estritamente em sanções administrativas no âmbito da Lei 12.846/2013, apresentando frequentemente penalidades de multa e publicação extraordinária em conjunto sob o mesmo processo.

---

## Fonte 4 — CNAE (Classificação Nacional de Atividades Económicas)

- **Origem Institucional:** Instituto Brasileiro de Geografia e Estatística (IBGE) / Comissão Nacional de Classificação (CONCLA).
- **URL de referência:** https://concla.ibge.gov.br
- **Meio Técnico e Coleta:** Não houve download direto da tabela CONCLA pelo script. Os códigos e descrições dos CNAEs foram recebidos estruturados no retorno JSON do serviço intermediário de dados cadastrais (`minhareceita.org`) e normalizados na tabela canónica `cnaes.csv` (36 códigos únicos) e `estabelecimento_cnaes.csv` (45 associações).

---

## Correspondência entre Fontes

- **Quantos registos de compliance possuem CNPJ identificável:**
  - CEIS: 14.603 registos de PJ (9.678 CNPJs únicos).
  - CNEP: 1.814 registos de PJ (1.032 CNPJs únicos).
  - CNPJs presentes em ambas as bases (interseção CEIS e CNEP): 282 empresas.
- **Quantos foram ligados exatamente ao cadastro CNPJ na amostra:**
  - Amostra canónica: 18 empresas completas com todos os vínculos (estabelecimentos, sócios, CNAEs e compliance).
  - Total de registos de sanção ligados às empresas da amostra: 54 sanções (38 do CEIS e 16 do CNEP).
- **Quantos permaneceram sem correspondência na amostra:**
  - 0 registos da amostra canónica: 100% dos registos de compliance em `data/processed/canonical/compliance.csv` possuem o respetivo `cnpj_sancionado` cadastrado em `estabelecimentos.csv` e `empresas.csv`.
- **Regra usada para ligar os registos:**
  - Vínculo estrito por identificador oficial: `compliance.csv (cnpj_sancionado)` == `estabelecimentos.csv (cnpj)` e `estabelecimentos.csv (cnpj_basico)` == `empresas.csv (cnpj_basico)`.
  - Nenhuma inferência ou correspondência foi efetuada por semelhança de nome ou razão social.
- **Casos ambíguos excluídos:**
  - Registos de sanções aplicadas a pessoas físicas (PF) com CPF;
  - Registos com `TIPO DE PESSOA` vazio ou sem identificador CNPJ válido no formato estrutural.

---

## Reprodutibilidade

Para reproduzir a amostra canónica a partir dos arquivos brutos descarregados:

1. Garantir os arquivos brutos nas pastas de origem:
   - `data/raw/20261105_CEIS.csv`
   - `data/raw/20261105_CNEP.csv`
2. Executar a auditoria dos arquivos de entrada:
   ```bash
   python scripts/audit_source_counts.py \
     --ceis data/raw/20261105_CEIS.csv \
     --cnep data/raw/20261105_CNEP.csv \
     --json data/processed/audit_source_counts.json