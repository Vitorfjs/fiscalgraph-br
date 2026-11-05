# Fontes e Recorte de Dados — FiscalGraph BR (Dev2)

Este documento registra a proveniência, metadados, regras de recorte e correspondência dos dados públicos empresariais e de sanções utilizados no protótipo do FiscalGraph BR.

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

---

## Fonte 1 — CNPJ / Receita Federal do Brasil (RFB)

- **URL oficial do conjunto:** https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj e repositório oficial https://www.gov.br/receitafederal/dados
- **Página de metadados/layout consultada e versão/data do documento:** Layout oficial PDF versão 2022 (`cnpj-metadados.pdf`) confrontado com as diretrizes do CNPJ Alfanumérico vigentes desde 31/07/2026.
- **A estrutura efetiva do arquivo tem cabeçalho? Se não, como a ordem de campos foi confirmada?**
  Os arquivos brutos compactados de dados abertos da Receita Federal tradicionalmente não possuem cabeçalho. A ordem dos campos foi confrontada com o layout oficial do CNPJ e validada por meio do espelho público/aberto da base da Receita Federal (implementado via serviço compatível de dados abertos da RFB).
- **URL oficial do espelho/dados consultados:** https://minhareceita.org/ (API aberta de espelho dos dados públicos da RFB).
- **Data e hora da consulta:** 05/11/2026 às 10:44.
- **Competência/referência do dataset:** 04/11/2026.
- **Nomes exatos dos arquivos baixados/utilizados:** `20261104_CEIS.csv` e `20261104_CNEP.csv` (para extração dos CNPJs de PJs sancionadas) + Dados Abertos da Receita Federal do Brasil (tabelas Empresas, Estabelecimentos, QSA e CNAEs).
- **Campos originais utilizados:**
  - `cnpj` / `cnpj_basico`: 14 caracteres textuais (12 alfanuméricos + 2 numéricos) e 8 caracteres básicos.
  - `razao_social`: Razão social da empresa.
  - `natureza_juridica`: Descrição da natureza jurídica.
  - `porte`: Porte empresarial (ME, EPP, DEMAIS).
  - `capital_social`: Valor declarado de capital social.
  - `nome_fantasia`: Nome de fantasia do estabelecimento.
  - `situacao_cadastral`: Descrição da situação cadastral (ATIVA, BAIXADA, etc.).
  - `data_inicio_atividade`: Data de abertura normalizada em `YYYY-MM-DD`.
  - `uf` e `municipio`: Localização geográfica do estabelecimento.
  - `cnae_fiscal` e `cnae_fiscal_descricao`: Atividade econômica principal.
  - `cnaes_secundarios`: Atividades econômicas secundárias.
  - `qsa`: Nome dos sócios, qualificação, identificador de tipo (PF/PJ) e data de ingresso.
- **Critério de recorte:**
  Seleção focada nas entidades que possuem sanções vigentes/registradas no CEIS e CNEP, com interseção comprovada por identificador exato (CNPJ de 14 posições).
- **Quantidade de linhas antes/depois:**
  - Base nacional: dezenas de milhões de registros.
  - Recorte canônico: 16 empresas, 16 estabelecimentos, 31 CNAEs, 39 vínculos estabelecimento-CNAE e 24 registros de sócios.
- **Limitações/observações:**
  - Preservado o formato de string para o CNPJ com zeros à esquerda.
  - Não há exportação de CPF bruto nem dados pessoais não públicos: os identificadores de sócio são sintéticos (`SOC-` + hash de escopo restrito).

---

## Fonte 2 — CEIS (Cadastro de Empresas Inidôneas e Suspensas)

- **URL oficial:** https://portaldatransparencia.gov.br/download-de-dados/ceis
- **Data e hora do download:** 05/11/2026 às 10:34:00-03:00.
- **Competência/data escolhida na página:** 04/11/2026.
- **Nome exato do arquivo e dicionário:**
  - Arquivo: `20261104_CEIS.csv` (tamanho: ~33.8 MB, codificação Latin-1, delimitador `;`).
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
  - Filtragem de registros de Pessoa Jurídica com CNPJ válido de 14 posições.
- **Quantidade de linhas antes/depois:**
  - Antes: 23.753 registros totais no arquivo bruto (14.585 PJ e 9.157 PF).
  - PJ com CNPJ válido de 14 posições: 9.658 CNPJs distintos.
  - No recorte canônico consolidado: 38 sanções do CEIS vinculadas às empresas da amostra.
- **Limitações/observações:**
  - Registros de pessoas físicas foram descartados para cumprir as diretrizes de minimização e proteção de dados.
  - Datas nulas ou descritas como "Sem Informação" foram transformadas em strings vazias.

---

## Fonte 3 — CNEP (Cadastro Nacional de Empresas Punidas)

- **URL oficial:** https://portaldatransparencia.gov.br/download-de-dados/cnep
- **Data e hora do download:** 05/11/2026 às 10:34:00-03:00.
- **Competência/data escolhida na página:** 04/11/2026.
- **Nome exato do arquivo e dicionário:**
  - Arquivo: `20261104_CNEP.csv` (tamanho: ~1.8 MB, codificação Latin-1, delimitador `;`).
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
  - `OBSERVAÇÕES`: Detalhes e observações registradas.
- **Critério de recorte:**
  - Apenas Pessoas Jurídicas com identificador CNPJ íntegro.
- **Quantidade de linhas antes/depois:**
  - Antes: 1.854 registros totais (1.814 PJ e 28 PF).
  - PJ com CNPJ válido de 14 posições: 1.032 CNPJs distintos.
  - No recorte canônico consolidado: 12 sanções do CNEP vinculadas às empresas da amostra.
- **Limitações/observações:**
  - O CNEP foca estritamente em sanções administrativas no âmbito da Lei 12.846/2013, apresentando frequentemente penalidades de multa e publicação extraordinária em conjunto sob o mesmo processo.

---

## Correspondência entre Fontes

- **Quantos registros de compliance possuem CNPJ identificável:**
  - CEIS: 14.585 registros de PJ (9.658 CNPJs únicos).
  - CNEP: 1.814 registros de PJ (1.032 CNPJs únicos).
  - CNPJs presentes em ambas as bases (interseção CEIS e CNEP): 282 empresas.
- **Quantos foram ligados exatamente ao cadastro CNPJ na amostra:**
  - Amostra canônica: 16 empresas completas com todos os vínculos (estabelecimentos, sócios, CNAEs e compliance).
  - Total de registros de sanção ligados às empresas da amostra: 50 sanções (38 do CEIS e 12 do CNEP).
- **Quantos permaneceram sem correspondência na amostra:**
  - 0 registros da amostra canônica: 100% dos registros de compliance em `data/processed/canonical/compliance.csv` possuem o respectivo `cnpj_sancionado` cadastrado em `estabelecimentos.csv` e `empresas.csv`.
- **Regra usada para ligar os registros:**
  - Vínculo estrito por identificador oficial: `compliance.csv (cnpj_sancionado)` == `estabelecimentos.csv (cnpj)` e `estabelecimentos.csv (cnpj_basico)` == `empresas.csv (cnpj_basico)`.
  - Nenhuma inferência ou correspondência foi feita por semelhança de nome ou razão social.
- **Casos ambíguos excluídos:**
  - Registros de sanções aplicadas a pessoas físicas (PF) com CPF;
  - Registros cadastrais que sofreram bloqueio transitório ou instabilidade durante a coleta cadastral (ex: CNPJs 00700484000181 e 00764466000163 que retornaram indisponibilidade temporária de consulta e foram excluídos do recorte para não deixar nós órfãos).

---

## Reprodutibilidade

Para reproduzir a amostra canônica a partir dos arquivos brutos baixados:

1. Garantir os arquivos brutos baixados nas pastas de origem:
   - `data/raw/20261104_CEIS.csv`
   - `data/raw/20261104_CNEP.csv`
2. Executar o pipeline de ingestão e estruturação canônica:
   ```bash
   python scripts/build_canonical_dataset.py
   ```
3. Executar o validador oficial do projeto:
   ```bash
   python scripts/validate_canonical_data.py --directory data/processed/canonical
   ```
4. O validador deve emitir saída com código de retorno 0:
   `Validação estrutural concluída. Revise os avisos e a qualidade semântica manualmente.`
