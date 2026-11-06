# FiscalGraph BR — Validação do Neo4j

> Preencher este documento somente com resultados efetivamente observados. Não declarar execução concluída com base apenas na existência dos scripts.

## 1. Ambiente utilizado

| Item | Valor observado |
| --- | --- |
| Neo4j | Neo4j Kernel 5.26.32 (Community Edition) |
| Execução | Docker Compose local (`fiscalgraph-neo4j`) |
| Data/hora da validação | 2026-11-06T15:16:24-03:00 |
| Responsável pela execução | Vitor Ferreira Gonçalves Silva |
| Branch/commit testado | `dev3` |

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

### 5.2. Contagem de Nós

| Rótulo (Label) | Resultado observado | Esperado (Snapshot Atual) | Status |
| --- | --- | --- | --- |
| Empresa | 18 | 18 | Conforme |
| Estabelecimento | 18 | 18 | Conforme |
| Socio | 26 | 26 | Conforme |
| CNAE | 36 | 36 | Conforme |
| Sancao | 54 | 54 | Conforme |
| Fonte | 4 | 4 | Conforme |
| Trecho | 0 | 0 | Previsto para Dev4 |
| **Total de Nós** | **156** | **156** | **Íntegro** |

### 5.3. Contagem de Relacionamentos Estruturados

| Tipo de Relacionamento | Resultado observado | Esperado (Snapshot Atual) | Status |
| --- | --- | --- | --- |
| APLICADA_A | 54 | 54 | Conforme |
| EXERCE_CNAE | 45 | 45 | Conforme |
| ORIGINADO_DE | 152 | 152 | Conforme |
| PARTICIPA_DE | 26 | 26 | Conforme |
| POSSUI_ESTABELECIMENTO | 18 | 18 | Conforme |
| **Total de Relacionamentos** | **295** | **295** | **Íntegro** |

*(Nota: os 152 relacionamentos `ORIGINADO_DE` ligam as 18 Empresas, 18 Estabelecimentos, 26 Sócios, 36 CNAEs e 54 Sanções às suas respetivas instâncias de Fonte).*

## 6. Idempotência

1. Anotar as contagens de nós e relacionamentos após a primeira carga:
* Total de nós: 156
* Total de relacionamentos: 295


2. Executar novamente `python scripts/load_canonical_data.py`.
3. Executar novamente as consultas de contagem no Neo4j Browser.
4. Confirmar que as contagens não aumentaram por duplicação.

Resultado observado:

* Total de nós após reexecução: 156 (variação: 0)
* Total de relacionamentos após reexecução: 295 (variação: 0)
* Conclusão: O carregador é estritamente idempotente através do uso de `MERGE`, sem criar duplicados.

## 7. Evidências

Os resultados das consultas de conferência de schema, índices e integridade foram exportados e versionados no diretório `docs/evidencias/`:

- `docs/evidencias/neo4j_query_table_data_2026-11-6-indexes.csv`: resultado de `SHOW INDEXES`, comprovando os 15 índices com estado `ONLINE`, incluindo `fiscalgraph_text_fulltext` cobrindo `texto` e `fundamentacao_legal`, e os índices de filtro `empresa_porte_idx` e `sancao_numero_processo_idx`.
- `docs/evidencias/neo4j_query_table_data_2026-11-6.csv`: resultado das contagens e checagens estruturais no Neo4j Browser (156 nós, 295 relacionamentos e zero registros órfãos).

Caso capturas visuais em formato de imagem (`.png`) sejam disponibilizadas no ambiente local, devem ser salvas sem conter credenciais, tokens ou variáveis de ambiente.

## 8. Limitações

* O carregador valida referências por identificadores e não realiza resolução de identidade por nome.
* CNPJ é mantido como texto; a validação estrutural não calcula os dígitos verificadores.
* Ausência de `data_fim` em uma sanção não prova vigência atual.
* Os dados representam o snapshot documentado nos arquivos de fonte.
* O índice vetorial e a geração de embeddings pertencem à etapa Dev5.
* O nó `Trecho` é gerado a partir dos campos textuais do registro de compliance; `MENCIONA` permanece como relação candidata.

---

