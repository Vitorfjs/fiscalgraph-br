# Execução da aplicação integrada — FiscalGraph BR

## Dependências

Em ambientes CPU, instale PyTorch CPU-only antes das dependências do projeto:

```bash
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
python -m pip install -r requirements.txt -r requirements-dev4.txt
```

## Neo4j e dados

1. Copie `.env.example` para `.env` e defina uma senha local forte.
2. Inicie o Neo4j definido em `infra/compose.yaml`.
3. Aplique o schema Cypher integrado.
4. Carregue os dados canônicos e os trechos conforme os scripts do projeto.
5. Gere os embeddings com `python scripts/generate_embeddings.py`.
6. Confirme que os índices vetorial e full-text estão ONLINE.

A consulta real pressupõe schema, dados, índices e embeddings preparados. A aplicação não cria dados nem gera embeddings automaticamente.

## LLM opcional

A integração aceita um endpoint compatível com OpenAI Chat Completions. Configure no `.env`:

- `LLM_CHAT_COMPLETIONS_URL`: URL completa do endpoint `/chat/completions`;
- `LLM_API_KEY`: chave do provedor;
- `LLM_MODEL`: identificador do modelo;
- `LLM_TIMEOUT_SECONDS`: timeout opcional (padrão 45).

Nunca versione o arquivo `.env` nem coloque chaves em commits, fixtures ou logs.

Sem as três primeiras variáveis, a aplicação usa uma síntese determinística dos trechos recuperados e informa essa condição em `warnings`. Isso não é uma resposta gerada por LLM.

## Executar

```bash
streamlit run app/streamlit_app.py
```

Selecione **Consulta real (Neo4j)** para executar a recuperação híbrida ou **Demonstração (Mock)** para usar fixtures sintéticas.

## Limites semânticos

- `retrieval_relevance` é relevância normalizada da recuperação, não probabilidade de fraude.
- `MENCIONA {status: CANDIDATA}` é menção textual pendente de validação, não vínculo jurídico confirmado.
- Nós e arestas exibidos são exclusivamente os retornados pelo mecanismo de recuperação.
- Ausência de resultados no recorte consultado não prova inexistência fora dos dados disponíveis.
