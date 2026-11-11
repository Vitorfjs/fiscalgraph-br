# FiscalGraph BR — Validação do Neo4j

> Preencher este documento somente com resultados efetivamente observados. Não declarar execução concluída com base apenas na existência dos scripts e não misturar evidências de ambientes distintos.

Este registro é dividido em três seções independentes:

1. **Validação Local Histórica (2026-11-06 — `dev4`):** carga canônica (Dev3) + Text-to-Graph (Dev4) antes da integração do Dev5.
2. **Validação Automatizada no CI (2026-11-11 — `main` / PR #9):** pipeline completo em Neo4j descartável (`neo4j:5.26-community`) com schema, dados canônicos, trechos, embeddings e suíte completa.
3. **Validação Local Pós-Integração Final (Pendente):** execução completa em ambiente local de desenvolvimento com a interface integrada.

---

# Parte A — Validação Local Histórica (2026-11-06 — `dev4`)

## 1. Ambiente utilizado

| Item | Valor observado |
| --- | --- |
| Neo4j | Neo4j Kernel 5.26.32 (Community Edition) |
| Execução | Docker Compose local (`fiscalgraph-neo4j`) |
| Data/hora da validação | 2026-11-06T15:16:24-03:00 |
| Responsável pela execução | Vitor Ferreira Gonçalves Silva |
| Branch/commit testado | `dev4` (anterior à integração Dev5) |

Consulta para registrar a versão:

```cypher
CALL dbms.components() YIELD name, versions, edition
RETURN name, versions, edition;
```

Resultado obtido:

* `name`: "Neo4j Kernel"
* `versions`: ["5.26.32"]
* `edition`: "community"

## 2. Preparação

1. Iniciar o container Neo4j já configurado pelo projeto.
2. Confirmar que `python scripts/check_neo4j.py` retorna conexão bem-sucedida.
3. Confirmar que os sete CSVs existem em `data/processed/canonical/`.
4. Executar primeiro `python scripts/load_canonical_data.py --dry-run`.
5. Não executar a carga real enquanto o dry-run apresentar erro.

Resultado do Dry-Run:

* `fontes.csv`: 4 registros
* `empresas.csv`: 18 registros
* `estabelecimentos.csv`: 18 registros
* `cnaes.csv`: 36 registros
* `estabelecimento_cnaes.csv`: 45 registros
* `socios.csv`: 26 registros
* `compliance.csv`: 54 registros

## 3. Criação do schema

Executar todos os comandos do arquivo `cypher/01_schema_fiscalgraph.cypher` no Neo4j Browser, um comando por vez.

O schema cria:

* 7 constraints de unicidade: `Empresa`, `Estabelecimento`, `Socio`, `CNAE`, `Sancao`, `Fonte` e `Trecho`;
* Índices de filtro para situação cadastral, localização, porte, tipo de registro e número de processo;
* 1 índice full-text compartilhado para campos textuais de `Empresa`, `Socio`, `Sancao` e `Trecho`.

As constraints de unicidade criam os respectivos índices de apoio. Não criar índices duplicados para as mesmas chaves.

## 4. Carga dos dados canônicos

Na raiz do repositório:

```bash
python scripts/load_canonical_data.py --dry-run
python scripts/load_canonical_data.py
```

O carregador usa `MERGE`, preserva os identificadores como strings e não apaga nós ou relacionamentos existentes. A execução repetida deve manter as contagens, sem duplicar entidades ou relações.

A carga deste script cria `Empresa`, `Estabelecimento`, `Socio`, `CNAE`, `Sancao` e `Fonte`. Os nós `Trecho` e seus relacionamentos são criados posteriormente pelo loader do Dev4.

## 5. Consultas de validação

Executar as consultas do arquivo `cypher/02_validacao_schema.cypher`, uma por vez. Registrar os resultados observados:

### 5.1. Validação Estrutural e de Integridade

| Verificação | Resultado observado | Esperado |
| --- | --- | --- |
| Constraints de unicidade | 7 constraints ativas | 7 constraints nomeadas |
| Índices | 15 índices (7 RANGE de apoio a constraints, 5 RANGE de filtro, 1 FULLTEXT com texto e fundamentacao_legal, e 2 LOOKUP); estado `ONLINE` | 15 índices criados; estado `ONLINE` |
| Estabelecimentos sem Empresa | 0 | 0 |
| Sócios sem Empresa | 0 | 0 |
| Sanções sem Estabelecimento de CNPJ exato | 0 | 0 |
| Entidades sem ORIGINADO_DE | 0 | 0 após as cargas correspondentes |

### 5.2. Contagem de Nós Canônicos (Dev3)

| Rótulo (Label) | Resultado observado | Esperado (Snapshot Canônico) | Status |
| --- | --- | --- | --- |
| Empresa | 18 | 18 | Conforme |
| Estabelecimento | 18 | 18 | Conforme |
| Socio | 26 | 26 | Conforme |
| CNAE | 36 | 36 | Conforme |
| Sancao | 54 | 54 | Conforme |
| Fonte | 4 | 4 | Conforme |
| **Total de Nós Canônicos** | **156** | **156** | **Íntegro** |

### 5.3. Contagem de Relacionamentos Estruturados Canônicos (Dev3)

| Tipo de Relacionamento | Resultado observado | Esperado (Snapshot Canônico) | Status |
| --- | --- | --- | --- |
| APLICADA_A | 54 | 54 | Conforme |
| EXERCE_CNAE | 45 | 45 | Conforme |
| ORIGINADO_DE | 152 | 152 | Conforme |
| PARTICIPA_DE | 26 | 26 | Conforme |
| POSSUI_ESTABELECIMENTO | 18 | 18 | Conforme |
| **Total de Relacionamentos** | **295** | **295** | **Íntegro** |

*(Nota: os 152 relacionamentos `ORIGINADO_DE` canônicos ligam as 18 Empresas, 18 Estabelecimentos, 26 Sócios, 36 CNAEs e 54 Sanções às suas respectivas instâncias de Fonte).*

## 6. Idempotência da Carga Canônica

1. Anotar as contagens de nós e relacionamentos após a primeira carga:
   * Total de nós: 156
   * Total de relacionamentos: 295
2. Executar novamente `python scripts/load_canonical_data.py`.
3. Executar novamente as consultas de contagem no Neo4j Browser.
4. Confirmar que as contagens não aumentaram por duplicação.

Resultado observado:

* Total de nós após reexecução: 156 (variação: 0)
* Total de relacionamentos após reexecução: 295 (variação: 0)
* Conclusão: o carregador é estritamente idempotente através do uso de `MERGE`, sem criar duplicados.

## 7. Evidências Exportadas (`2026-11-06`)

Os resultados das consultas de conferência de schema, índices e integridade foram exportados e versionados no diretório `docs/evidencias/`:

* `docs/evidencias/neo4j_query_table_data_2026-11-6-indexes.csv`: resultado de `SHOW INDEXES`, comprovando os 15 índices com estado `ONLINE`, incluindo `fiscalgraph_text_fulltext` cobrindo `texto` e `fundamentacao_legal`, e os índices de filtro `empresa_porte_idx` e `sancao_numero_processo_idx`.
* `docs/evidencias/neo4j_query_table_data_2026-11-6-constraints.csv`: resultado das contagens e checagens estruturais no Neo4j Browser (156 nós, 295 relacionamentos e zero registros órfãos).
* `docs/evidencias/neo4j_query_table_data_dev4_integrado.csv`: resultado da consulta consolidada de nós e arestas após a carga de Dev4, comprovando 210 nós (incluindo 54 Trechos), 405 relacionamentos (incluindo 54 `EXTRATO_DE`, 54 `ORIGINADO_DE` de trechos e 2 `MENCIONA`) e a estabilidade das contagens pós-reexecução.

Caso capturas visuais em formato de imagem (`.png`) sejam disponibilizadas no ambiente local, devem ser salvas sem conter credenciais, tokens ou variáveis de ambiente.

## 8. Validação da Extensão Text-to-Graph (Dev4)

A etapa Text-to-Graph transforma os campos textuais das sanções em nós `Trecho` e extrai menções textuais de CNPJ vinculando-as como candidatas ao grafo.

### 8.1. Resultados da Carga Integrada

Execução na raiz do repositório:

```bash
python -m pipeline.text_to_graph.load_graph --input data/processed/trechos.jsonl --batch-size 200
```

Métricas observadas no console e validadas no Neo4j:

* **Trechos carregados**: 54 nós criados.
* **Registros de compliance não encontrados**: 0 (54/54 conectados via `EXTRATO_DE`).
* **Fontes não encontradas**: 0 (54/54 conectados via `ORIGINADO_DE`).
* **Menções CNPJ ligadas como CANDIDATA**: 2 (correspondência exata com `Estabelecimento.cnpj`, com offsets `inicio` e `fim` preservados).
* **Menções CNPJ não resolvidas**: 0.
* **Menções ORGANIZACAO carregadas**: 0 (artefato gerado em modo regex estrutural determinístico).

### 8.2. Censo Consolidado do Grafo (Pós Dev3 + Dev4)

| Elemento | Rótulo / Tipo | Carga Canônica (Dev3) | Carga Text-to-Graph (Dev4) | Total Consolidado |
| --- | --- | --- | --- | --- |
| **Nós** | `Empresa` | 18 | 0 | 18 |
|  | `Estabelecimento` | 18 | 0 | 18 |
|  | `Socio` | 26 | 0 | 26 |
|  | `CNAE` | 36 | 0 | 36 |
|  | `Sancao` | 54 | 0 | 54 |
|  | `Fonte` | 4 | 0 | 4 |
|  | `Trecho` | 0 | +54 | **54** |
| **Total de Nós** |  | **156** | **+54** | **210** |
| **Relacionamentos** | `APLICADA_A` | 54 | 0 | 54 |
|  | `EXERCE_CNAE` | 45 | 0 | 45 |
|  | `PARTICIPA_DE` | 26 | 0 | 26 |
|  | `POSSUI_ESTABELECIMENTO` | 18 | 0 | 18 |
|  | `ORIGINADO_DE` | 152 | +54 | **206** |
|  | `EXTRATO_DE` | 0 | +54 | **54** |
|  | `MENCIONA` | 0 | +2 | **2** |
| **Total de Relações** |  | **295** | **+110** | **405** |

### 8.3. Idempotência e Integridade Referencial da Carga de Trechos

A reexecução do script `load_graph.py` com `--batch-size 200` manteve as contagens estritamente em **210 nós** e **405 relacionamentos**, comprovando idempotência total:

```cypher
// Verificação de ausência de registros órfãos
MATCH (t:Trecho) WHERE NOT (t)-[:EXTRATO_DE]->(:Sancao) RETURN count(t) AS trechos_sem_sancao; // Retorna 0
MATCH (t:Trecho) WHERE NOT (t)-[:ORIGINADO_DE]->(:Fonte) RETURN count(t) AS trechos_sem_fonte;  // Retorna 0
```

---

# Parte B — Validação Automatizada no CI (2026-11-11 — `main` / PR #9)

Após a incorporação do módulo Dev5 e da integração E2E (PR #9), os workflows do GitHub Actions executaram o pipeline completo em ambiente limpo:

| Item | Valor observado |
| --- | --- |
| Data | 2026-11-11 |
| Runner / Serviço | `ubuntu-latest`, Python 3.11 + `neo4j:5.26-community` descartável |
| Workflows | `.github/workflows/dev5-ci.yml` e `.github/workflows/integration-e2e.yml` |
| Runs de referência | `43107457046` e `43107457065` |
| Etapas executadas no CI | Aplicação de `cypher/01_schema_fiscalgraph.cypher`, `load_canonical_data.py`, `pipeline/text_to_graph/load_graph.py`, `scripts/generate_embeddings.py --batch-size 32` e `unittest discover` |
| Resultado observado | **147 testes aprovados** (incluindo testes unitários e de integração contra Neo4j populado com índice vetorial `trecho_embedding_vector` e `fiscalgraph_text_fulltext` ativos) |

*(Nota: a validação no CI comprova a execução automatizada do backend e dos testes em Neo4j descartável; não substitui a validação manual da aplicação e interface Streamlit em ambiente local.)*

---

# Parte C — Validação Local Pós-Integração Final (2026-11-11 — `main`)

Execução completa em ambiente local macOS após a integração de Dev1, Dev5 e Dev6 na `main`, com Python 3.12.12 (`.venv`) e container `fiscalgraph-neo4j` (`neo4j:5-community`).

| Item | Valor observado |
| --- | --- |
| Data/hora da execução | 2026-11-11T20:24:12-03:00 |
| Versão do Neo4j local (`CALL dbms.components()`) | Neo4j Kernel `5.26.33` (Community Edition) |
| Branch de referência | `main` (pós-PR #9) |
| Constraints de unicidade | 7 constraints ativas (`Empresa`, `Estabelecimento`, `Socio`, `CNAE`, `Sancao`, `Fonte`, `Trecho`) |
| Índices (`SHOW INDEXES`) | 16 índices `ONLINE` (`100.0%`), incluindo `fiscalgraph_text_fulltext` (FULLTEXT) e `trecho_embedding_vector` (VECTOR, 384d, `cosine`) |
| Total de nós / relacionamentos | **210 nós** (`18 Empresa`, `18 Estabelecimento`, `26 Socio`, `36 CNAE`, `54 Sancao`, `4 Fonte`, `54 Trecho`) e **405 relacionamentos** (`26 PARTICIPA_DE`, `18 POSSUI_ESTABELECIMENTO`, `45 EXERCE_CNAE`, `54 APLICADA_A`, `206 ORIGINADO_DE`, `54 EXTRATO_DE`, `2 MENCIONA`) |
| Embeddings (`generate_embeddings.py`) | **54/54** trechos com embedding, dimensão `384/384`, norma L2 `1.000000/1.000000`, `150` janelas (`máx. 8`), `0` tokens não representados, versão `v2-janelas-126-sobreposicao-32-media-ponderada-tokens-novos-l2`; `--dry-run` posterior com `0` pendentes |
| Integridade referencial (`cypher/02_validacao_schema.cypher`) | `0` estabelecimentos sem empresa, `0` sócios sem vínculo `PARTICIPA_DE`, `0` sanções sem estabelecimento, `0` CNAEs inválidos, `0` entidades sem `ORIGINADO_DE`, `0` trechos sem sanção ou fonte |
| Idempotência pós-reexecução | Reexecução de `load_canonical_data.py` e `load_graph.py` manteve exatamente 210 nós e 405 relacionamentos |
| Suíte `unittest` local | **150 testes aprovados em 14.389s** (`OK`, 0 falhas, 0 skips) |

*(Observação: durante a validação local, foi corrigida a consulta F de `cypher/02_validacao_schema.cypher` para verificar a ausência da aresta `(s:Socio)-[:PARTICIPA_DE]->(:Empresa)`, pois `:Socio` não armazena `cnpj_basico` como propriedade de nó no loader canônico e na modelagem LPG.)*

---

## Limitações Registradas

* O carregador valida referências por identificadores e não realiza resolução de identidade por nome.
* CNPJ é mantido como texto; a validação estrutural não calcula os dígitos verificadores.
* Ausência de `data_fim` em uma sanção não prova vigência atual.
* Os dados representam o snapshot documentado nos arquivos de fonte (competência 04/11/2026, coleta em 05/11/2026).
* O nó `Trecho` é gerado a partir dos campos textuais do registro de compliance; `MENCIONA` permanece como relação candidata (`status = "CANDIDATA"`).
