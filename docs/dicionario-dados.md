# Dicionário de Dados Canónicos — FiscalGraph BR (Dev2)

Este documento descreve o contrato canónico de dados gerado pela branch `dev2`, mapeando a origem de cada campo, regras de transformação e premissas adotadas.

---

## 1. Mapeamento dos Campos Canónicos

| Arquivo canónico | Campo canónico | Campo na fonte | Transformação / normalização | Obrigatório? | Observações |
|---|---|---|---|---|---|
| **fontes.csv** | `fonte_id` | Identificador interno | Atribuição de código fixo com prefixo `F-` (ex: `F-CGU-CEIS`) | Sim | Chave primária da fonte |
| **fontes.csv** | `nome` | Nome da base | Nomenclatura oficial do conjunto de dados | Sim | Texto livre descritivo |
| **fontes.csv** | `orgao_responsavel` | Órgão emissor | Nome completo e sigla oficial do órgão | Sim | Ex: CGU, RFB, IBGE |
| **fontes.csv** | `url` | Endereço do portal | URL canónica oficial de download ou metadados | Sim | Endereço rastreável |
| **fontes.csv** | `data_coleta` | Timestamp da coleta | Formato ISO-8601 com fuso horário (`YYYY-MM-DDTHH:MM:SS-03:00`) | Sim | Momento exato da extração |
| **fontes.csv** | `competencia` | Data dos dados na página | Formato `YYYY-MM-DD` | Sim | Data de referência do arquivo |
| **fontes.csv** | `arquivo_origem` | Nome do arquivo baixado | Nome do arquivo original baixado na pasta `data/raw/` | Sim | Rastreabilidade do arquivo |
| **empresas.csv** | `cnpj_basico` | Primeiros 8 dígitos do CNPJ | String de 8 caracteres alfanuméricos preservando zeros à esquerda | Sim | Chave primária da entidade Empresa |
| **empresas.csv** | `razao_social` | `razao_social` (RFB) / `RAZÃO SOCIAL - CADASTRO RECEITA` | Remoção de espaços extras e pontuações espúrias | Sim | Nome empresarial oficial |
| **empresas.csv** | `natureza_juridica` | `natureza_juridica` (RFB) | Descrição textual da natureza jurídica | Não | Ex: Sociedade Empresária Limitada |
| **empresas.csv** | `porte` | `porte` (RFB) | Normalizado (ME, EPP, DEMAIS) | Não | Porte cadastral |
| **empresas.csv** | `capital_social` | `capital_social` (RFB) | Valor decimal/numérico sem pontuação de milhar | Não | Vazio se não informado |
| **empresas.csv** | `fonte_id` | `fonte_id` | Referência à fonte primária cadastral (`F-RFB-CNPJ`) | Sim | Chave estrangeira para `fontes.csv` |
| **empresas.csv** | `registro_origem` | Chave de auditoria | Identificador composto `ReceitaFederal:CNPJ:{cnpj}` | Sim | Rastreabilidade de proveniência |
| **estabelecimentos.csv** | `cnpj` | `cnpj` (RFB) / `CPF OU CNPJ DO SANCIONADO` | String de exatamente 14 caracteres alfanuméricos | Sim | Chave primária do Estabelecimento |
| **estabelecimentos.csv** | `cnpj_basico` | 8 primeiros caracteres do `cnpj` | Extração substring `cnpj[:8]` | Sim | Relacionamento 1:N com Empresa |
| **estabelecimentos.csv** | `nome_fantasia` | `nome_fantasia` (RFB) | Limpeza de texto | Não | Vazio quando não cadastrado |
| **estabelecimentos.csv** | `situacao_cadastral` | `descricao_situacao_cadastral` (RFB) | Texto descritivo (ATIVA, BAIXADA, SUSPENSA, etc.) | Não | Situação perante a RFB |
| **estabelecimentos.csv** | `data_inicio_atividade` | `data_inicio_atividade` (RFB) | Conversão para formato `YYYY-MM-DD` | Não | Vazio se não disponível |
| **estabelecimentos.csv** | `uf` | `uf` (RFB) | Sigla de 2 caracteres em maiúsculas | Não | Unidade Federativa |
| **estabelecimentos.csv** | `municipio` | `municipio` (RFB) | Nome padronizado do município em maiúsculas | Não | Localidade |
| **estabelecimentos.csv** | `fonte_id` | `fonte_id` | `F-RFB-CNPJ` | Sim | Vínculo de procedência |
| **estabelecimentos.csv** | `registro_origem` | Chave de auditoria | `ReceitaFederal:Estabelecimento:{cnpj}` | Sim | Rastreabilidade |
| **cnaes.csv** | `codigo` | `codigo` / `cnae_fiscal` (RFB/IBGE) | String numérica do código CNAE (ex: `1081302`) | Sim | Chave primária da Atividade |
| **cnaes.csv** | `descricao` | `descricao` / `cnae_fiscal_descricao` | Texto descritivo da atividade económica | Sim | Descrição oficial CONCLA |
| **cnaes.csv** | `fonte_id` | `fonte_id` | `F-IBGE-CNAE` | Sim | Órgão responsável pela tabela |
| **cnaes.csv** | `registro_origem` | Chave de auditoria | `IBGE:CONCLA:{codigo}` | Sim | Rastreabilidade |
| **estabelecimento_cnaes.csv** | `cnpj` | `cnpj` do estabelecimento | String de 14 caracteres | Sim | Chave estrangeira composta |
| **estabelecimento_cnaes.csv** | `codigo` | `cnae_fiscal` ou secundário | Código CNAE associado | Sim | Chave estrangeira composta |
| **estabelecimento_cnaes.csv** | `principal` | Classificação da atividade | Booleano textual (`True` para fiscal principal, `False` para secundário) | Sim | Distinção de relevância |
| **estabelecimento_cnaes.csv** | `fonte_id` | `fonte_id` | `F-RFB-CNPJ` | Sim | Procedência do vínculo |
| **estabelecimento_cnaes.csv** | `registro_origem` | Chave de auditoria | `ReceitaFederal:CNAE:{cnpj}` | Sim | Rastreabilidade |
| **socios.csv** | `socio_id` | Identificador sintético | Prefixo `SOC-` seguido de hash SHA256 truncado (`cnpj_basico + index + nome`) | Sim | Identificador sintético de ocorrência local. Não deduplica pessoas entre empresas. |
| **socios.csv** | `cnpj_basico` | 8 caracteres da empresa | String de 8 caracteres alfanuméricos | Sim | Vínculo societário com Empresa |
| **socios.csv** | `nome` | `nome_socio` (RFB) | Nome civil ou razão social do sócio | Sim | Titular da participação |
| **socios.csv** | `tipo_pessoa` | `identificador_de_socio` (RFB) | Mapeado para `PESSOA FISICA` (se 2) ou `PESSOA JURIDICA` | Sim | Natureza da pessoa do sócio |
| **socios.csv** | `qualificacao` | `qualificacao_socio` (RFB) | Cargo/condição societária (ex: Sócio-Administrador, Sócio) | Não | Descrição da atuação |
| **socios.csv** | `data_entrada` | `data_entrada_sociedade` (RFB) | Conversão para `YYYY-MM-DD` | Não | Início do vínculo societário |
| **socios.csv** | `fonte_id` | `fonte_id` | `F-RFB-CNPJ` | Sim | Procedência cadastral |
| **socios.csv** | `registro_origem` | Chave de auditoria | `ReceitaFederal:QSA:{cnpj}:S{index}` | Sim | Rastreabilidade por linha/posição no QSA |
| **compliance.csv** | `registro_id` | Prefixo + `CÓDIGO DA SANÇÃO` | Identificador único estável (ex: `CEIS-132342`, `CNEP-132344`) | Sim | Chave primária da Sanção |
| **compliance.csv** | `tipo_registro` | `CADASTRO` | `CEIS` ou `CNEP` | Sim | Categoria do cadastro de sanção |
| **compliance.csv** | `orgao_responsavel` | `ÓRGÃO SANCIONADOR` | Nome do órgão aplicador da penalidade | Não | Autoridade pública sancionadora |
| **compliance.csv** | `numero_processo` | `NÚMERO DO PROCESSO` | String com numeração do processo administrativo | Não | Vazio se não houver |
| **compliance.csv** | `data_inicio` | `DATA INÍCIO SANÇÃO` | Conversão de `DD/MM/YYYY` para `YYYY-MM-DD` | Não | Vigência inicial da sanção |
| **compliance.csv** | `data_fim` | `DATA FINAL SANÇÃO` | Conversão de `DD/MM/YYYY` para `YYYY-MM-DD` | Não | Término (vazio se indeterminado) |
| **compliance.csv** | `situacao` | `ABRAGÊNCIA DA SANÇÃO` | Alcance/esfera da punição aplicada | Não | Esfera de proibição |
| **compliance.csv** | `descricao` | `CATEGORIA DA SANÇÃO` | Modalidade da sanção imposta | Não | Ex: Inidoneidade, Multa |
| **compliance.csv** | `observacoes` | `OBSERVAÇÕES` | Texto complementar da autoridade sancionadora | Não | Notas do processo |
| **compliance.csv** | `fundamentacao_legal` | `FUNDAMENTAÇÃO LEGAL` | Dispositivo de lei referenciado | Não | Ex: Lei 8.666/93, Lei 12.846/13 |
| **compliance.csv** | `cnpj_sancionado` | `CPF OU CNPJ DO SANCIONADO` | String de exatamente 14 caracteres (apenas PJ) | Sim | Chave para ligação com Estabelecimento |
| **compliance.csv** | `fonte_id` | `fonte_id` | `F-CGU-CEIS` ou `F-CGU-CNEP` | Sim | Chave estrangeira de fonte |
| **compliance.csv** | `url_fonte` | URL direta | Link oficial do Portal da Transparência | Sim | Link público de download |
| **compliance.csv** | `registro_origem` | Nome do arquivo + linha | Ex: `20261105_CEIS.csv:L3805`, `20261105_CNEP.csv:L59` | Sim | Rastreabilidade exata na fonte |

---

## 2. Regras de Privacidade, Segurança e Semântica

1. **Minimização de Dados Pessoais:** Nenhuma coluna ou valor referente a CPF bruto é persistido nas tabelas canónicas[cite: 4].
2. **Escopo Semântico do `socio_id`:** O identificador sintético `socio_id` representa estritamente uma ocorrência/posição no snapshot atual do Quadro de Sócios e Administradores (QSA) associado a uma empresa específica (`cnpj_basico + index + nome`)[cite: 4]. **Não deve ser utilizado para deduplicar pessoas nem para inferir ou afirmar identidade/homonímia entre sócios de empresas distintas.**
3. **Identificação Rigorosa por CNPJ:** Registos de sanções (compliance) são vinculados às entidades exclusivamente por correspondência exata do identificador oficial `cnpj_sancionado`[cite: 4]. Nenhuma inferência ou correspondência probabilística é realizada a partir de similaridade textual de razões sociais ou nomes de fantasia[cite: 4].