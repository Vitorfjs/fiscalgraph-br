# Execução da aplicação integrada — FiscalGraph BR

## 1. Pré-requisitos e dependências

Utilize Python 3.11 (referência do CI) ou 3.12+ em ambiente virtual dedicado. Em ambientes CPU, instale o PyTorch CPU-only antes das demais dependências para evitar o download dos pacotes CUDA:

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

## 2. Configuração do `.env`

1. Copie `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```
2. Defina uma senha local forte em `NEO4J_PASSWORD` (não deixe o valor padrão de exemplo) e confira `NEO4J_URI=bolt://localhost:7687`, `NEO4J_USER=neo4j` e `NEO4J_DATABASE=neo4j`.
3. Confirme que `.env` continua listado em `.gitignore`. Nunca versione credenciais, tokens ou chaves em commits, fixtures ou capturas de tela.

## 3. Validação prévia, Neo4j e carga do pipeline

1. Valide os CSVs canônicos e o arquivo de trechos antes de abrir o banco:
   ```bash
   python scripts/validate_canonical_data.py
   python scripts/validate_canonical_relations.py
   python scripts/load_canonical_data.py --dry-run
   python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl --dry-run
   ```
2. Inicie o Neo4j definido em `infra/compose.yaml` e confira a conectividade:
   ```bash
   docker compose --env-file .env -f infra/compose.yaml up -d
   python scripts/check_neo4j.py
   ```
   *(O Compose usa volume persistente; `docker compose down` preserva os dados, enquanto `down -v` apaga o banco local.)*
3. Aplique e valide o schema pelo script do projeto (idempotente):
   ```bash
   python scripts/apply_schema.py
   ```
   O script executa os comandos declarativos com `IF NOT EXISTS`, aguarda a criação dos índices e verifica as 7 constraints e os 6 índices de busca. O Neo4j Browser (`http://localhost:7474`) pode ser usado para inspeção, mas não é necessário para essa etapa.
4. Execute a carga dos dados canônicos e confirme a idempotência na reexecução:
   ```bash
   python scripts/load_canonical_data.py
   ```
5. Execute a carga dos trechos e menções candidatas (`Text-to-Graph`):
   ```bash
   python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl
   ```
6. Gere os embeddings de 384 dimensões e garanta que o índice vetorial `trecho_embedding_vector` esteja `ONLINE`:
   ```bash
   python scripts/generate_embeddings.py --dry-run
   python scripts/generate_embeddings.py --batch-size 32
   ```
7. Confira as verificações de `cypher/02_validacao_schema.cypher`, além de `SHOW CONSTRAINTS;` e `SHOW INDEXES;` (ambos `fiscalgraph_text_fulltext` e `trecho_embedding_vector` devem estar `ONLINE`).

> A consulta real pressupõe schema, dados, índices e embeddings preparados. A aplicação Streamlit não cria dados nem gera embeddings automaticamente.

## 4. LLM opcional e controle de envio de evidências

A integração aceita um endpoint compatível com OpenAI Chat Completions. Configure no `.env`:

- `LLM_CHAT_COMPLETIONS_URL`: URL completa do endpoint `/chat/completions`;
- `LLM_API_KEY`: chave do provedor;
- `LLM_MODEL`: identificador do modelo;
- `LLM_SEND_EVIDENCE`: flag explícita de opt-in (`false` por padrão);
- `LLM_TIMEOUT_SECONDS`: timeout opcional em segundos (padrão `45`).

Regras de operação e privacidade:

- **Envio desativado por padrão:** mantenha `LLM_SEND_EVIDENCE=false` durante desenvolvimento e validação inicial. Mesmo que URL, chave e modelo estejam preenchidos, `app/services/orchestrator.py` **não** enviará os trechos recuperados a um provedor externo enquanto `LLM_SEND_EVIDENCE` não for exatamente `true`.
- **Condição para ativação:** só configure `LLM_SEND_EVIDENCE=true` após aprovação explícita do grupo, considerando a natureza pública/sensível dos dados e a política de privacidade do provedor utilizado.
- **Fallback determinístico:** sem as variáveis de LLM configuradas, com `LLM_SEND_EVIDENCE=false` ou em caso de falha/resposta inválida do provedor, a aplicação gera uma síntese determinística a partir dos trechos recuperados e registra essa condição em `warnings`. Essa síntese nunca é apresentada como saída de LLM.

## 5. Executar a interface e testes

```bash
streamlit run app/streamlit_app.py
```

- Selecione **Consulta real (Neo4j)** para executar a recuperação híbrida com os dados carregados.
- Selecione **Demonstração (Mock)** para testar os cenários sintéticos de sucesso e abstenção sem depender do Neo4j.

Para validar a suíte de testes:

```bash
python -m compileall -q app pipeline scripts tests
python -m unittest discover -s tests -v
```

## 6. Limites semânticos

- `retrieval_relevance` é relevância normalizada da recuperação, não probabilidade de fraude.
- `MENCIONA {status: "CANDIDATA"}` é menção textual pendente de validação, não vínculo jurídico confirmado.
- Nós e arestas exibidos são exclusivamente os retornados pelo mecanismo de recuperação.
- Ausência de resultados no recorte consultado não prova inexistência fora dos dados disponíveis.
