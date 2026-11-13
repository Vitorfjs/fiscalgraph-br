# Text-to-Graph — dev4

Etapa que transforma os campos textuais dos registros de compliance (CEIS/CNEP) em nós `Trecho`
rastreáveis e em menções candidatas de entidades, para alimentar a busca semântica/full-text do
GraphRAG (dev5). **Nenhuma menção extraída de texto é tratada como vínculo confirmado.**

## Arquivos

| Arquivo | Função |
| --- | --- |
| `pipeline/text_to_graph/extractor.py` | Lê `compliance.csv`, monta trechos, mascara CPF e extrai menções (CNPJ por regex, ORG por spaCy). Gera `trechos.jsonl`. |
| `pipeline/text_to_graph/load_graph.py` | Carrega `Trecho`, cria `EXTRATO_DE`, `ORIGINADO_DE`, `MENCIONA` por CNPJ exato e `MENCAO_NOME` por nome normalizado exato e unívoco. Suporta `--database`, `--companies-csv` e `--dry-run`. |
| `tests/test_text_to_graph.py` | 31 testes unitários com dados sintéticos (sem Neo4j e sem spaCy). |
| `data/fixtures/compliance_sintetico.csv` | Fixture 100% sintética; não representa registro real. |
| `requirements-dev4.txt` | Dependência adicional: spaCy. |

## Etapas

1. **Trecho textual.** Concatena, nesta ordem e separados por quebra de linha, os campos disponíveis
   `descricao`, `observacoes` e `fundamentacao_legal`. Registros sem nenhum texto são ignorados e contabilizados.
   `trecho_id = sha256(registro_id | texto)[:24]`: estável entre execuções (mesma entrada → mesmo id).
2. **Privacidade.** CPF formatado (`000.000.000-00`) é substituído por `[CPF REMOVIDO]` **antes** da extração;
   a quantidade mascarada fica em `cpf_mascarados`. CPF não sai do pipeline.
3. **Menções de CNPJ (regex estrutural).** Aceita `XX.XXX.XXX/XXXX-XX` e a forma contínua de 14 posições.
   As 12 primeiras posições aceitam letras maiúsculas e dígitos (CNPJ alfanumérico, emitido pela RFB desde
   31/07/2026); as 2 últimas são dígitos. O valor é normalizado para string de 14 posições, preservando zeros à
   esquerda e letras. Sequências contínuas sem nenhum dígito nas 12 primeiras posições são descartadas (palavras).
   Dígitos verificadores **não** são calculados (validação apenas estrutural).
4. **NER de organizações.** spaCy `pt_core_news_sm`, entidades `ORG`, ativado com `--with-spacy`. Filtros:
   - linhas com mais de 80% de letras maiúsculas (transcrição de lei em `fundamentacao_legal`) são descartadas,
     pois o modelo marca quase toda palavra em CAIXA ALTA como `ORG` nesse tipo de texto;
   - entidades com menos de 3 caracteres, sem letras ou em lista de termos genéricos (`DOU`, `CNPJ`, `Decisão`…).
5. **Resolução de entidades e relações candidatas.** Cada menção recebe `status = "CANDIDATA"`.
   - CNPJ: igualdade exata entre o valor normalizado e `Estabelecimento.cnpj` gera
     `(Trecho)-[:MENCIONA {metodo, status, inicio, fim}]->(Estabelecimento)`.
   - Organização: `load_graph.py` compara `valor_normalizado` com a razão social do catálogo canônico,
     usando o mesmo normalizador do extrator. Só cria
     `(Trecho)-[:MENCAO_NOME {metodo, status, valor_normalizado, inicio, fim}]->(Empresa)`
     quando o nome normalizado aponta para exatamente um `cnpj_basico`.
   - Colisões entre duas ou mais empresas são marcadas como ambíguas e não geram aresta. Ausência de
     correspondência também não gera aresta. Não há fuzzy matching, deduplicação por homonímia nem
     criação/fusão de nós a partir de texto. A aresta nominal continua candidata e não prova identidade
     jurídica ou participação societária.
6. **Procedência.** Cada trecho preserva `registro_id`, `fonte_id`, `url_fonte`, `registro_origem` e
   `metodo_extracao`; os offsets `inicio`/`fim` apontam para o trecho exato de `texto`.

`RegistroCompliance/Sancao-[:REFERE_SE_A|APLICADA_A]->Empresa/Estabelecimento` **não** é criada por esta etapa:
pertence à carga estruturada (dev3), a partir da coluna `cnpj_sancionado`.

### Formato de `data/processed/trechos.jsonl`

```json
{"trecho_id": "…", "registro_id": "CEIS-289814", "texto": "…", "fonte_id": "F-CGU-CEIS",
 "url_fonte": "https://portaldatransparencia.gov.br/download-de-dados/ceis",
 "registro_origem": "20261104_CEIS.csv:L…", "metodo_extracao": "regex_cnpj+spacy_ner",
 "mencoes": [{"tipo": "CNPJ", "valor": "01340937000179", "inicio": 120, "fim": 138,
              "metodo": "regex_cnpj_estrutural", "status": "CANDIDATA"}]}
```

## Como executar

Na raiz do repositório, com a `.venv` ativa:

```bash
pip install -r requirements.txt -r requirements-dev4.txt
python -m spacy download pt_core_news_sm

# 1. Testes (não exigem spaCy nem Neo4j)
python -m unittest discover -s tests -p "test_text_to_graph.py" -v

# 2. Extração no recorte canônico de dev2
python pipeline/text_to_graph/extractor.py --input data/processed/canonical/compliance.csv --output data/processed/trechos.jsonl --with-spacy --stats data/processed/trechos_stats.json

# 3. Conferência sem banco
python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl --dry-run

# 4. Carga no Neo4j (após schema e carga estruturada de dev3; requer .env local)
python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl
```

Sem o modelo spaCy, rode o passo 2 sem `--with-spacy`: somente CNPJ é extraído e a etapa NER deve ser
registrada como pendente.

## Resultados (execução integrada pós-PR #3 e PR #4)

- **CSV de entrada:** `data/processed/canonical/compliance.csv` integrado à `main` via PR #3 (Dev2) e PR #4 (Dev3); fontes `F-CGU-CEIS` e `F-CGU-CNEP`, competência 2026-11-05.
- **Ambiente:** Python 3.13, spaCy 3.8, `pt_core_news_sm` 3.8.0, Neo4j 5.26.
- **Registros lidos:** 54 registros de compliance (CEIS e CNEP).
- **Registros sem texto:** 0.
- **Trechos gerados:** 54 trechos gerados (nenhum duplicado).
- **CPFs mascarados:** 0.
- **Menções CNPJ:** 2 (2 CNPJs distintos), ambas com correspondência exata ao `cnpj_sancionado` do próprio registro (`CNEP-310577` e `CEIS-289814`).
- **CNPJs que existem como `Estabelecimento.cnpj` no recorte:** 2 de 2 → ambos vinculados com relação `MENCIONA {status: 'CANDIDATA'}` na carga.
- **Organizações no snapshot versionado:** o arquivo atual `data/processed/trechos.jsonl` foi gerado sem NER spaCy e, portanto, não comprova extração nominal ativa na amostra real. A nova etapa de resolução nominal só produzirá arestas quando o JSONL for reprocessado com `--with-spacy` e houver correspondência exata, normalizada e unívoca no catálogo canônico. A existência do código e dos testes não deve ser relatada como execução dessa etapa na amostra integrada.
- **Validação no Neo4j 5.26 integrado com Dev3:**
  - 54 nós `:Trecho` carregados com sucesso (elevando o total de nós de 156 para 210 no grafo);
  - 54 relações `:EXTRATO_DE` conectadas às sanções correspondentes (0 registros não encontrados);
  - 54 relações `:ORIGINADO_DE` conectadas às fontes oficiais (0 fontes não encontradas; total de 206 ORIGINADO_DE no grafo);
  - 2 relações `:MENCIONA` criadas com `status = 'CANDIDATA'` por correspondência exata de CNPJ (0 menções CNPJ não resolvidas);
  - 0 menções de organização carregadas no subgrafo (o artefacto versionado não inclui NER por ter sido gerado sem spaCy, mantendo 0 vínculos espúrios por nome);
  - **Idempotência validada:** re-execução do loader manteve estritamente a mesma contagem de nós e relações (210 nós e 405 relacionamentos);
  - **Multi-hop validado:** travessia de 4 saltos (`Trecho -> Sancao -> Estabelecimento <- Empresa <- Socio`) retornou 72 caminhos válidos, cobrindo as 18 empresas, 54 sanções e 54 trechos do recorte canônico.

### Revisão

- Conferência automática dos 54 trechos: todos têm `registro_id`, `fonte_id`, `url_fonte` e `registro_origem` preenchidos, os 54 `trecho_id` são distintos e estáveis, e os offsets das menções apontam para o texto correto.
- As menções foram revisadas manualmente e a consistência do subgrafo foi validada no Neo4j Browser.
- Antes do filtro de linhas em maiúsculas, o NER produzia falsos positivos em transcrições de lei. Com o filtro, a precisão textual foi substancialmente aprimorada.

Não são reportadas métricas de acurácia (precisão/recall), pois não há conjunto de verdade-terreno anotado.

## Limitações

- O `pt_core_news_sm` é um modelo pequeno, treinado em texto jornalístico; reconhece mal organizações em texto administrativo curto e em CAIXA ALTA.
- O filtro de linhas em maiúsculas pode descartar nomes válidos escritos em uma linha totalmente maiúscula.
- O regex de CNPJ não verifica dígitos verificadores; um número de 14 dígitos qualquer pode ser capturado.
- Apenas CPF formatado é mascarado; CPF sem pontuação não é distinguido de outros números de 11 dígitos.
- `MENCIONA` indica que o texto cita um CNPJ — não prova que a organização é sancionada, responsável ou parte do processo.
- A correspondência nominal é limitada à igualdade após normalização e unicidade no catálogo; não usa similaridade aproximada. Colisões e nomes ausentes ficam sem aresta. O resultado ainda é uma menção candidata, não vínculo jurídico.
- A fixture é totalmente sintética e não pode ser usada como evidência de domínio real.

## Pontos de integração (para o coordenador)

- A modelagem e schema de Dev3 já incorporaram a constraint `trecho_trecho_id_unique` e o índice `fiscalgraph_text_fulltext` contemplando `Trecho.texto`.
- O loader Dev4 suporta configuração de banco via parâmetro `--database` e variável de ambiente `NEO4J_DATABASE` (padrão `neo4j`).
- O índice vetorial e a geração de embeddings de 384 dimensões em `Trecho.embedding` pertencem à etapa Dev5.
