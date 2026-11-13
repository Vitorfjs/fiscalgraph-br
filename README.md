# FiscalGraph BR

> Projeto final da disciplina **Tendências em Ciência da Computação** — Bacharelado em Ciência da Computação, 2026.

## Objetivo

O **FiscalGraph BR** é um protótipo acadêmico de **GraphRAG** sobre **Neo4j** que integra dados cadastrais públicos de empresas brasileiras (CNPJ/QSA/CNAE) e registros públicos de sanções administrativas (**CEIS** e **CNEP**), permitindo consultas explicáveis com fontes, trechos documentais e caminhos no grafo.

> **Aviso metodológico e uso responsável:** Uma ligação societária, coincidência de nome, atividade CNAE compartilhada, menção textual ou registro em cadastro público **não constitui, isoladamente, prova de fraude, sonegação, culpa ou irregularidade atual**. O sistema apoia análise preliminar rastreável e não substitui auditoria ou decisão jurídica.

---

## Arquitetura Geral

1. **Dados Canônicos e Normalização (`scripts/` + `data/processed/canonical/`):** recorte determinístico de 18 CNPJs (interseção e exclusivos de CEIS/CNEP), com preservação de identificadores em string, exclusão de pessoas físicas nas sanções e geração de `socio_id` sintético sem exposição de CPF bruto.
2. **Modelagem LPG no Neo4j (`cypher/`):** nós `Empresa`, `Estabelecimento`, `Socio`, `CNAE`, `Sancao`, `Fonte` e `Trecho`, com constraints de unicidade e índices de filtro, full-text (`fiscalgraph_text_fulltext`) e vetorial (`trecho_embedding_vector`).
3. **Pipeline Text-to-Graph (`pipeline/text_to_graph/`):** extração de nós `Trecho` a partir dos textos de compliance com preservação de procedência, mascaramento de CPF formatado e vinculação de menções de CNPJ como relações `MENCIONA` com `status = "CANDIDATA"`.
4. **Recuperação Híbrida e Multi-hop (`app/services/retrieval.py`, `embeddings.py`, `ranking.py`, `multi_hop.py`):** embeddings de 384 dimensões (`paraphrase-multilingual-MiniLM-L12-v2`), busca vetorial + busca full-text combinadas por **Reciprocal Rank Fusion (RRF)**, expansão de subgrafo e consultas multi-hop entre empresas.
5. **Orquestração (`app/services/orchestrator.py`, `response_adapter.py`, `contract.py`):** validação de contrato, síntese determinística transparente e suporte opcional a endpoint compatível com OpenAI Chat Completions (opt-in via `LLM_SEND_EVIDENCE=true`).
6. **Interface Streamlit (`app/streamlit_app.py`, `mock_service.py`, `source_adapter.py`):** alternância explícita entre **Consulta real (Neo4j)** e **Demonstração (Mock)**, exibição de fontes/trechos e visualização interativa do subgrafo com `streamlit-agraph`.

---

## Tecnologias

- **Python** (testado no CI com 3.11; compatível com 3.12/3.13)
- **Neo4j 5 Community** (`infra/compose.yaml`, `neo4j>=5.18.1`)
- **Sentence Transformers + PyTorch (CPU)** (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensões)
- **Streamlit** + **streamlit-agraph** + **pandas**
- **spaCy** (opcional para NER experimental em `pipeline/text_to_graph/extractor.py`)

---

## Estrutura do Repositório

```text
.
├── .github/workflows/           # Workflows de CI (dev5-ci.yml e integration-e2e.yml)
├── app/
│   ├── services/                # Recuperação híbrida, embeddings, multi-hop, orquestração e adaptadores
│   └── streamlit_app.py         # Interface web Streamlit (Consulta real + Modo Mock)
├── cypher/                      # Schema, consultas de validação, multi-hop e índice vetorial
├── data/
│   ├── fixtures/                # Fixture sintética para testes do extractor
│   ├── processed/
│   │   ├── canonical/           # 7 CSVs canônicos versionados + build_report.json
│   │   ├── audit_source_counts.json
│   │   └── trechos.jsonl        # 54 trechos extraídos com procedência e menções candidatas
│   ├── raw/                     # Ignorado pelo Git (arquivos brutos CEIS/CNEP locais)
│   └── templates/               # Modelos de cabeçalho dos CSVs canônicos
├── diagrams/                    # Diagrama conceitual (.mmd, .dot, .png, .svg)
├── docs/                        # Documentação técnica, contrato de integração, evidências e exemplos
├── fixtures/                    # Fixtures sintéticas do Modo Mock (sucesso e abstenção)
├── infra/compose.yaml           # Serviço Docker do Neo4j 5 Community
├── pipeline/text_to_graph/      # Extrator e carregador de Trecho e MENCIONA
├── scripts/                     # Schema, validação, carga canônica, embeddings e auditorias
├── tests/                       # Suíte automatizada (unittest)
├── .env.example
├── requirements.txt
├── requirements-ci.txt
├── requirements-dev4.txt
└── requirements-dev5.txt
```

---

## Instalação

Recomenda-se Python 3.11 (conforme o CI) ou 3.12+ com ambiente virtual isolado:

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
python -m pip install -r requirements.txt -r requirements-ci.txt
```

### Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
python -m pip install -r requirements.txt -r requirements-ci.txt
```

> Instalar o PyTorch CPU-only antes de `requirements.txt` evita downloads desnecessários de pacotes CUDA em máquinas sem GPU.

---

## Configuração do `.env`

Copie o modelo e ajuste as credenciais locais (nunca versione o `.env`):

```bash
cp .env.example .env
```

Principais variáveis:

```env
NEO4J_USER=neo4j
NEO4J_PASSWORD=sua_senha_local_forte
NEO4J_URI=bolt://localhost:7687
NEO4J_DATABASE=neo4j

# LLM opcional (compatível com OpenAI Chat Completions)
LLM_CHAT_COMPLETIONS_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_SEND_EVIDENCE=false
LLM_TIMEOUT_SECONDS=45
```

- Sem `LLM_CHAT_COMPLETIONS_URL`, `LLM_API_KEY` e `LLM_MODEL`, a aplicação utiliza **síntese determinística** a partir dos trechos recuperados.
- Mesmo quando configurado, o envio de evidências ao provedor externo só ocorre se `LLM_SEND_EVIDENCE=true` for definido explicitamente.

---

## Como Iniciar o Neo4j e Carregar o Grafo

### 1. Validar os arquivos canônicos localmente

```bash
python scripts/validate_canonical_data.py
python scripts/validate_canonical_relations.py
python scripts/load_canonical_data.py --dry-run
python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl --dry-run
```

### 2. Iniciar o container Neo4j

```bash
docker compose --env-file .env -f infra/compose.yaml up -d
python scripts/check_neo4j.py
```

O Neo4j Browser fica disponível em `http://localhost:7474` (o volume em `infra/compose.yaml` é persistente; evite `docker compose down -v` se não quiser apagar os dados).

### 3. Aplicar schema, carregar dados e gerar embeddings

1. Aplique o schema de forma automatizada e idempotente:
   ```bash
   python scripts/apply_schema.py
   ```
   O script lê as credenciais do `.env`, aguarda os índices e falha se as 7 constraints ou os 6 índices de busca esperados não estiverem disponíveis/ONLINE. O Neo4j Browser continua disponível para inspeção, mas não é necessário para essa etapa.
2. Carregue os CSVs canônicos (18 empresas, 18 estabelecimentos, 26 sócios, 36 CNAEs, 45 vínculos CNAE, 54 sanções, 4 fontes):
   ```bash
   python scripts/load_canonical_data.py
   ```
3. Carregue os 54 trechos e 2 menções candidatas:
   ```bash
   python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl
   ```
4. Gere os embeddings (384 dimensões) e garanta o índice vetorial `trecho_embedding_vector`:
   ```bash
   python scripts/generate_embeddings.py --dry-run
   python scripts/generate_embeddings.py --batch-size 32
   ```
5. Execute as consultas de `cypher/02_validacao_schema.cypher` e verifique `SHOW CONSTRAINTS` e `SHOW INDEXES` (`ONLINE`).

Consulte também `docs/EXECUCAO_APLICACAO_INTEGRADA.md` para detalhes operacionais, `docs/CHECKLIST_ENTREGA_FINAL.md` para reprodução limpa e `docs/ROTEIRO_APRESENTACAO_FINAL.md` para a demonstração.

---

## Como Executar a Interface Streamlit

```bash
streamlit run app/streamlit_app.py
```

### Modos disponíveis na barra lateral

- **Consulta real (Neo4j):** executa a recuperação híbrida (vetorial + full-text + RRF) no Neo4j local, expande o subgrafo e monta a resposta via `app/services/orchestrator.py`. Exige Neo4j ativo, dados carregados e embeddings gerados.
- **Demonstração (Mock):** carrega fixtures sintéticas (`fixtures/resposta_completa_mock.json` e `fixtures/resposta_abstencao_mock.json`) para demonstrar os cenários de sucesso e abstenção sem depender do Neo4j ou de embeddings. Os resultados exibidos são explicitamente sinalizados como sintéticos.

---

## Como Executar os Testes

### Suíte unitária (sem Neo4j)

```bash
python -m unittest discover -s tests -v
```

*(Quando `NEO4J_PASSWORD` não está configurado, os testes de integração dependentes de banco são ignorados com `skip`.)*

### Suíte completa (com Neo4j carregado e embeddings gerados)

```bash
python -m compileall -q app pipeline scripts tests
python -m unittest discover -s tests -v
```

### Avaliação quantitativa (Benchmark + Multi-hop no Neo4j)

```bash
python scripts/evaluate_retrieval_benchmark.py --k 5
```

---

## Documentação Complementar

- `docs/definicao-projeto.md` — problema, objetivos e escopo acadêmico.
- `docs/fontes-datasets.md` — procedência das fontes (RFB/Minha Receita, CEIS, CNEP, IBGE/CNAE) e reprodutibilidade.
- `docs/dicionario-dados.md` — contrato dos 7 CSVs canônicos e regras de minimização de dados.
- `docs/modelagem-lpg.md` — modelagem conceitual de nós, propriedades e relacionamentos.
- `docs/text-to-graph.md` — pipeline de extração de `Trecho` e menções `MENCIONA (CANDIDATA)`.
- `docs/recuperacao-hibrida.md` — embeddings, busca vetorial/full-text, RRF e multi-hop.
- `docs/CONTRATO_INTEGRACAO_FINAL.md` — contrato entre recuperação, orquestração e interface.
- `docs/politica-abstencao.md` — regras verificáveis de abstenção, fallback determinístico e verificação de citações.
- `docs/EXECUCAO_APLICACAO_INTEGRADA.md` — guia operacional de execução integrada.
- `docs/validacao-neo4j.md` — registros de validação do schema, cargas, índices e UI/benchmark.
- `docs/evidencias/dev5_benchmark_recuperacao.md` — benchmark rotulado (20 perguntas em 10 categorias) e análise multi-hop real vs. sintética.
- `docs/RELATORIO_ENTREGA_ACADEMICA.md` — consolidação de evidências, limitações e cenários de aceitação.
- `docs/CHECKLIST_ENTREGA_FINAL.md` — checklist de reprodução limpa e submissão.
- `docs/ROTEIRO_APRESENTACAO_FINAL.md` — roteiro de demonstração em aproximadamente 8 minutos.

---

## Limitações do Protótipo

- **Amostra reduzida (snapshot):** o recorte contém 18 empresas, 18 estabelecimentos, 26 registros de sócios, 54 sanções (30 CEIS + 24 CNEP) e 54 trechos referentes à competência documentada em 04/11/2026 (coleta em 05/11/2026), não representando consulta em tempo real à base nacional.
- **Serviço intermediário cadastral:** os dados cadastrais do CNPJ foram obtidos via serviço de terceiros (`minhareceita.org`) que espelha dados públicos da RFB.
- **Validação estrutural de CNPJ:** aceita o formato de 14 posições (compatível com CNPJ alfanumérico), sem cálculo de dígitos verificadores.
- **Identidade de sócios (`socio_id`):** chave técnica local por ocorrência no QSA da empresa; não deduplica pessoas físicas entre empresas distintas.
- **Menções `MENCIONA`:** possuem `status = "CANDIDATA"` e representam apenas ocorrências textuais de CNPJ, não vínculo jurídico confirmado.
- **Caminhos multi-hop:** nos 153 pares de empresas do recorte canônico atual, não há caminho societário real; os caminhos identificados são estruturais por CNAE compartilhado (atividade declarada em comum, não vínculo societário ou comercial).
- **Ausência de inferência jurídica:** o sistema não determina fraude, culpa ou responsabilidade legal; `rrf_score` e `retrieval_relevance` medem apenas relevância de recuperação.


> **Reprodutibilidade das dependências:** os arquivos `requirements*.txt` declaram versões mínimas, não um lockfile de versões exatas. Use Python 3.11 (referência do CI) e registre o ambiente efetivamente usado na validação local com `python --version` e `python -m pip freeze`. Os CSVs canônicos e os trechos utilizados na demonstração já estão versionados; os arquivos brutos originais em `data/raw/` não estão.
