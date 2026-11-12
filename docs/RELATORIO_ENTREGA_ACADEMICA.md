# Consolidação de Evidências, Limitações e Roteiro de Apresentação — FiscalGraph BR

**Data de consolidação:** 2026-11-11  
**Banco validado localmente:** Neo4j Kernel `5.26.33` (Community Edition, via `infra/compose.yaml`)  
**Suíte automatizada completa:** **177 testes aprovados** (0 falhas, 0 skips)

---

## 1. Arquitetura Ponta a Ponta e Módulos Integrados

| Módulo | Responsabilidade principal | Artefatos-chave |
| --- | --- | --- |
| **Dev2 — Dados e Normalização** | Recorte canônico de 18 CNPJs (RFB/Minha Receita, CEIS, CNEP, IBGE/CNAE), padronização de identificadores e validação estrutural pré-carga. | `data/processed/canonical/*.csv`, `scripts/validate_canonical_data.py`, `scripts/validate_canonical_relations.py`, `docs/dicionario-dados.md` |
| **Dev3 — Modelagem LPG e Neo4j** | Schema declarativo (7 constraints, índices de filtro, full-text), ingestão idempotente via `MERGE` e auditoria de integridade referencial. | `cypher/01_schema_fiscalgraph.cypher`, `cypher/02_validacao_schema.cypher`, `scripts/load_canonical_data.py`, `docs/modelagem-lpg.md` |
| **Dev4 — Text-to-Graph** | Extração determinística de trechos textuais com preservação de procedência e criação de arestas `MENCIONA {status: "CANDIDATA"}` com offsets. | `pipeline/text_to_graph/`, `data/processed/trechos.jsonl`, `docs/text-to-graph.md` |
| **Dev5 — Recuperação Híbrida e Multi-hop** | Embeddings `384d` (`paraphrase-multilingual-MiniLM-L12-v2`, janelas de 126 tokens), busca vetorial + full-text Lucene, fusão RRF (`k=60`), expansão do subgrafo e `shortestPath` (`company_paths`). | `app/services/retrieval.py`, `app/services/multi_hop.py`, `app/services/benchmark.py`, `scripts/generate_embeddings.py`, `scripts/evaluate_retrieval_benchmark.py` |
| **Dev1 — Orquestração e Abstenção** | Validação do contrato Dev5, política verificável de abstenção, síntese determinística, LLM opt-in (`LLM_SEND_EVIDENCE=true`) com verificação de citações e adaptador final. | `app/services/orchestrator.py`, `app/services/response_adapter.py`, `docs/politica-abstencao.md` |
| **Dev6 — Interface Streamlit** | Modos separados (**Consulta real (Neo4j)** e **Demonstração (Mock)**), fontes rastreáveis, visualização interativa com diferenciação de `MENCIONA (CANDIDATA)` e status Neo4j. | `app/streamlit_app.py`, `app/services/ui_helpers.py`, `app/services/source_adapter.py`, `app/services/mock_service.py` |

---

## 2. Evidências Quantitativas Consolidadas

### 2.1. Grafo, Embeddings e Índices (Neo4j Local + Idempotência)

- **Volumetria exata do grafo:** **210 nós** (`18 Empresa`, `18 Estabelecimento`, `26 Socio`, `36 CNAE`, `54 Sancao`, `4 Fonte`, `54 Trecho`) e **405 relacionamentos** (`26 PARTICIPA_DE`, `18 POSSUI_ESTABELECIMENTO`, `45 EXERCE_CNAE`, `54 APLICADA_A`, `206 ORIGINADO_DE`, `54 EXTRATO_DE`, `2 MENCIONA`).
- **Idempotência:** reexecução de `scripts/load_canonical_data.py` e `pipeline/text_to_graph/load_graph.py` preservou exatamente 210 nós e 405 arestas; `cypher/02_validacao_schema.cypher` retornou zero órfãos/inconsistências em todas as consultas (A–G).
- **Embeddings:** **54/54** `Trecho` cobertos integralmente (`150` janelas no total, máximo `8`, `0` tokens não representados), `384` dimensões, norma L2 `1.000000` em todos os vetores, versão `v2-janelas-126-sobreposicao-32-media-ponderada-tokens-novos-l2`.
- **Índices:** `16/16` índices `ONLINE` (`100%`), incluindo `fiscalgraph_text_fulltext` e `trecho_embedding_vector` (`cosine`, `384d`).

### 2.2. Benchmark Rotulado de Recuperação (20 Perguntas em 10 Categorias, `k = 5`)

Fonte reproduzível: `python scripts/evaluate_retrieval_benchmark.py --k 5` -> `docs/evidencias/dev5_benchmark_recuperacao.md` e `docs/evidencias/dev5_benchmark_metricas.json`.

| Modo avaliado | Consultas positivas | Precision@5 | Recall@5 | MRR@5 | nDCG@5 | Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Vetorial puro** (`trecho_embedding_vector`) | 16 | 0.1750 | 0.4353 | 0.4479 | 0.4065 | 0.5625 |
| **Full-text puro** (`fiscalgraph_text_fulltext`) | 16 | 0.4125 | 0.9821 | 1.0000 | 1.0000 | 1.0000 |
| **Híbrido (RRF `k=60`)** | 16 | 0.3000 | 0.7061 | 0.6250 | 0.6218 | 0.8125 |

**Achados empíricos relevantes para discussão acadêmica:**
1. **Vantagem observada do Full-text neste benchmark:** o Full-text isolado superou o híbrido RRF nas métricas agregadas Precision@5 (0.4125 vs. 0.3000), Recall@5 (0.9821 vs. 0.7061), MRR@5 (1.0000 vs. 0.6250) e nDCG@5 (1.0000 vs. 0.6218). O RRF melhorou o resultado vetorial puro, mas não foi o melhor modo de recuperação neste conjunto. A conclusão é específica ao recorte jurídico-documental e às 16 consultas positivas avaliadas; não deve ser generalizada para outros corpora.
2. **Complementaridade e efeito do RRF não ponderado (1:1):** no recorte de 54 trechos com termos legais densos, o full-text Lucene obteve `MRR@5 = 1.0000` (zero falhas) ao pontuar números de lei (`13.303`, `10.520`), DOU/Decisões (`247`, `209`, `250`, `414`), CNPJs e siglas (`REFIS`, `CFIL`). O vetor denso puro perdeu `7/16` consultas por diluição em textos jurídicos padronizados (`LEI 8666`, `LEI 12846`). A fusão RRF 1:1 superou fortemente o vetorial puro em `MRR@5` (`0.4479 -> 0.6250`) e `Hit@5` (`0.5625 -> 0.8125`), perdendo apenas `3/16` consultas (`Q05`, `Q07`, `Q10`) onde trechos genéricos ranquearam bem simultaneamente nos dois índices via `OR` de palavras comuns (`sanções`, `lei`, `artigo`).
2. **Política de Abstenção (Dev1 + Dev5):** atingiu **100.0% de acurácia (`20/20`)** — `16/16` respostas com evidências (`TN=16`) e `4/4` abstenções corretas (`TP=4`) para CNPJs ausentes do recorte (`Q17`, `Q18`) e consultas fora do domínio (`Q19`, `Q20`), zerando `sources`, `nodes` e `relationships` em toda abstenção.
3. **Multi-hop Real vs. Sintético:** nos 4 pares representativos reais (`00356328×01340937`, `00000113×00000145`, `00073357×01278154`, `00002776×00356328`), o serviço `company_paths` encontrou **3 caminhos estruturais por atividade econômica declarada em comum (`EXERCE_CNAE`, 4 saltos)** e **0 caminhos societários (`PARTICIPA_DE`)** no recorte canônico. O padrão societário multi-hop de **2 saltos** (`Empresa <- Socio -> Empresa`) foi demonstrado e testado de forma isolada em transação sintética com `rollback` automático.

---

## 3. Matriz de Verificação dos 12 Cenários de Aceitação

| # | Cenário de aceitação | Verificação executada | Status observado |
| --- | --- | --- | --- |
| 1 | Conexão ativa Neo4j na UI (`210` nós / `405` arestas, sem deprecation warning `01N00`) | `AppTest` real + `tests/test_streamlit_app.py` | Aprovado |
| 2 | Estado inicial da interface sem erro com aviso acadêmico | `AppTest` (`test_initial_render_shows_disclaimer_status_and_controls`) | Aprovado |
| 3 | Submissão com pergunta em branco exibe alerta sem chamar o grafo | `AppTest` (`test_empty_submission_displays_warning`) | Aprovado |
| 4 | Modo Demonstração (Mock) — Sucesso (fixture sintética + legenda) | `AppTest` (`test_mock_success_mode_renders_answer_sources_cypher_and_graph_metrics`) | Aprovado |
| 5 | Modo Demonstração (Mock) — Abstenção (sem fontes e sem subgrafo) | `AppTest` (`test_mock_abstention_mode_renders_error_and_no_subgraph`) | Aprovado |
| 6 | Consulta Real no domínio (`"Quais empresas foram declaradas inidôneas no CEIS?"`) | `AppTest` contra Neo4j real (`21` nós, `23` arestas, `5` fontes, `1` menção candidata) | Aprovado |
| 7 | Consulta Real com CNPJ literal na 2ª posição (`01.340.937/0001-79`) + priorização e aviso | `answer_question` + `AppTest` real (`27` nós, `27` arestas, `2` menções candidatas, `5` fontes) | Aprovado |
| 8 | Consulta Real de CNPJ ausente do recorte (`99.999.999/0001-99`) aciona abstenção | `answer_question` + `AppTest` real (`abstained=True`, `sources=[]`, `nodes=[]`) | Aprovado |
| 9 | Consulta fora do domínio (`"receita de bolo de chocolate"`) aciona abstenção sem LLM | `answer_question` + `AppTest` real (`abstained=True`, `sources=[]`, `nodes=[]`) | Aprovado |
| 10 | Diferenciação visual de `MENCIONA (CANDIDATA)` (vermelho tracejado) e legenda de nós | `test_build_graph_elements_styles_nodes_filters_dangling_edges_and_marks_candidates` | Aprovado |
| 11 | Falha de conexão / erro no Neo4j na UI sem expor segredos (`.env`) | `test_real_mode_connection_error_shows_safe_technical_details` | Aprovado |
| 12 | LLM opcional desabilitado por padrão e rejeição de identificador inventado | `tests/test_orchestrator.py` (`13` testes unitários) | Aprovado |

---

## 4. Limitações Consolidados por Módulo (Para Apresentação Crítica)

- **Recorte de dados (Dev2):** amostra acadêmica estática de **18 empresas** e **54 sanções** (competência 04/11/2026); ausência de registro ou de vínculo no recorte **não** equivale a certidão negativa na base pública nacional. CNPJs são validados estruturalmente (14 posições, suporte alfanumérico), sem cálculo dos dígitos verificadores. `socio_id` é chave técnica por ocorrência no QSA e não deduplica CPFs entre empresas.
- **Modelagem e grafo (Dev3/Dev4):** `MENCIONA` permanece estritamente com `status = "CANDIDATA"` e exige validação humana; nenhuma relação é criada por similaridade nominal.
- **Recuperação híbrida (Dev5):** embeddings densos (`MiniLM`) não distinguem dígitos de CNPJ e diluem trechos jurídicos longos repetitivos; na fusão RRF 1:1 com `OR` no full-text, palavras genéricas compartilhadas podem elevar trechos padronizados acima de correspondências literais pontuais (mitigado por `identifier_matches` e avisos explícitos). O recorte real possui apenas caminhos multi-hop via `CNAE` (atividade em comum, nunca vínculo societário).
- **Orquestração e LLM (Dev1):** por padrão (`LLM_SEND_EVIDENCE=false`), a resposta usa síntese determinística transparente; quando ativado por opt-in, textos recuperados são tratados como dados não confiáveis e citações inventadas são bloqueadas pelo verificador (`_verify_llm_grounding`). `retrieval_relevance` e `rrf_score` jamais devem ser lidos como probabilidade jurídica ou de fraude.
- **Interface (Dev6):** protótipo local em Streamlit para demonstração explicável; a visualização exibe apenas nós e arestas retornados pelo Neo4j na consulta corrente.

---

## 5. Roteiro Cronometrado de Demonstração Acadêmica (~10–12 minutos)

1. **Preparação prévia (antes da banca — 2 min antes):**
   - Confirmar Neo4j ativo (`docker ps` -> `fiscalgraph-neo4j`) e banco populado (`python scripts/check_neo4j.py`).
   - Iniciar a interface em um terminal: `.venv/bin/streamlit run app/streamlit_app.py`.
   - Ter um terminal secundário pronto caso a banca solicite inspeção da suíte ou do benchmark.
2. **Abertura e Arquitetura (~2 min):**
   - Apresentar o problema de compliance público e a motivação do GraphRAG explicável (evidência + fonte + caminho no grafo + política de abstenção, evitando "caixas-pretas").
   - Mostrar o painel **"Status da conexão Neo4j"** na UI (`210` nós / `405` relacionamentos) e o disclaimer acadêmico permanente no topo.
3. **Demonstração Real — Consulta de Domínio e Visualização do Grafo (~3 min):**
   - Pesquisar: `"Quais empresas foram declaradas inidôneas no CEIS?"` (`top_k = 5`).
   - Destacar: síntese determinística sem LLM externo (`warnings`), `Fontes e evidências utilizadas (5)` com trechos e URLs originais, `Consulta Cypher` auditável, métricas de subgrafo (`21` nós, `23` relacionamentos, `1` menção candidata) e legenda de cores distinguindo `MENCIONA (CANDIDATA)` em vermelho tracejado.
4. **Demonstração Crítica — CNPJ Literal e Transparência RRF (~2 min):**
   - Pesquisar: `"Qual a situação do CNPJ 01.340.937/0001-79?"`.
   - Mostrar como o sistema sinaliza explicitamente quando o CNPJ literal está em posição ≥ 2 do RRF e prioriza `CEIS-289814` (`[Correspondência literal de CNPJ]`) na resposta explicável, sem ocultar a limitação vetorial sobre números.
5. **Demonstração de Segurança Epistêmica — Abstenção e Modo Mock (~2 min):**
   - Testar `"Qual a situação do CNPJ 99.999.999/0001-99?"` e `"receita de bolo de chocolate"` -> mostrar abstenção imediata (`st.error`), explicação clara do limite do recorte/escopo e subgrafo vazio (zero alucinação).
   - Alternar rapidamente para **"Demonstração (Mock)"** na barra lateral para demonstrar o funcionamento desacoplado do banco com fixtures sintéticas sinalizadas.
6. **Resultados Quantitativos e Encerramento (~2 min):**
   - Exibir a tabela comparativa do benchmark (`Vetorial` vs. `Full-text` vs. `Híbrido RRF`), destacar **100% de acurácia de abstenção (20/20)** e a diferença entre multi-hop real por `CNAE` (`4` saltos) e o teste societário sintético (`PARTICIPA_DE`, `2` saltos), encerrando com as limitações registradas e os **177 testes aprovados**.

### Sugestões de Capturas de Tela para Anexar ao Relatório/Slides
1. Tela inicial mostrando disclaimer acadêmico + `Status da conexão Neo4j` (`210` nós / `405` relacionamentos).
2. Resultado completo de `"Qual a situação do CNPJ 01.340.937/0001-79?"` com fontes expandidas e subgrafo `agraph` evidenciando aresta vermelha tracejada `MENCIONA (CANDIDATA)`.
3. Tela de abstenção para `"receita de bolo de chocolate"` evidenciando ausência de fontes/grafo fabricados.
4. Terminal exibindo saída de `python scripts/evaluate_retrieval_benchmark.py --k 5` e `unittest discover` (`177 tests ... OK`).
