# Contrato de integração final — FiscalGraph BR

**Revisão:** 2026-11-11 (pós-merge do PR #9 na `main`)  
**Base técnica:** branch `main` (integração de Dev5 + Dev1 + Dev6)  
**Objetivo:** registrar o formato de integração entre recuperação (Dev5), orquestração/resposta (Dev1) e interface (Dev6), garantindo aderência semântica e rastreabilidade ponta a ponta.

## 1. Estado verificado do repositório (`main`)

| Módulo | Estado observado na `main` | Situação operacional |
| --- | --- | --- |
| Dev5 — recuperação híbrida | Serviço (`app/services/retrieval.py`), contrato (`app/services/contract.py`), embeddings (`app/services/embeddings.py`), ranking RRF (`app/services/ranking.py`), multi-hop (`app/services/multi_hop.py`) e suíte unitária/integração estão integrados na `main`. | Validado no CI com Neo4j descartável; pronto para consumo pela orquestração. |
| Dev1 — orquestração e resposta | `app/services/orchestrator.py` e `app/services/response_adapter.py` integrados na `main` (PR #9). Validam o contrato Dev5, produzem síntese determinística ou chamada opcional a LLM (`LLM_SEND_EVIDENCE=true`) e montam o JSON final. | Integrado; política ampliada de abstenção (fora de domínio, evidência insuficiente, busca parcial) e verificação de citações em refinamento final. |
| Dev6 — interface | `app/streamlit_app.py`, `app/services/source_adapter.py`, `app/services/mock_service.py` e `fixtures/` integrados na `main` (PR #9). Suportam **Consulta real (Neo4j)** e **Demonstração (Mock)** separados. | Integrado; falta validação visual local com Neo4j populado, refinamentos de legenda/evidências e testes automatizados de UI. |

> **Nota histórica:** o PR #6 (branch `dev6`, fase apenas Mock) e o PR #8 (branch `dev1-integracao` -> `dev1`, adaptador isolado) antecederam o PR #9 (`integracao-e2e` -> `main`). Na `main`, tanto `response_adapter.py` quanto `source_adapter.py` e a interface integrada já estão incorporados.

## 2. Contrato de entrada/saída do Dev5

Ponto de entrada:

```python
from app.services.retrieval import retrieve_context

context = retrieve_context(question, top_k=5)
```

A resposta contém:

- `query`, `retrieval_mode`, `cypher`, `warnings` e `parameters`;
- `chunks[]`, com `trecho_id`, `texto`, `registro_id`, `fonte_id`, `url_fonte`, ranks, scores, `rrf_score`, `graph_paths` e `identifier_matches`;
- `nodes[]`, no formato `{id, label, properties}`;
- `relationships[]`, no formato `{source, target, type, properties}`.

Validar antes do consumo:

```python
from app.services.contract import validate_retrieval_response

problems = validate_retrieval_response(context)
if problems:
    raise ValueError("Contrato Dev5 inválido: " + "; ".join(problems))
```

O Dev5 retorna evidências; não redige a resposta em linguagem natural nem decide a política completa de abstenção.

## 3. Formato da resposta final do Dev1

O formato final consumido pela interface é montado por `app/services/response_adapter.py` e `app/services/orchestrator.py`:

```json
{
  "answer": "Resposta redigida pelo Dev1 com base nas evidências",
  "cypher": "consulta usada pelo Dev5",
  "sources": [
    {
      "id": "registro_id ou trecho_id",
      "label": "Sancao ou Trecho",
      "url": "URL da fonte ou null",
      "excerpt": "Trecho textual usado como evidência"
    }
  ],
  "nodes": [],
  "relationships": [],
  "retrieval_relevance": 0.0,
  "abstained": false,
  "warnings": []
}
```

Regras de mapeamento implementadas:

| Campo final | Origem/regra |
| --- | --- |
| `answer` | Produzido por `orchestrator.py` via síntese determinística (`_deterministic_answer`) ou via endpoint LLM opcional (`_llm_answer`, apenas quando configurado e com `LLM_SEND_EVIDENCE=true`). |
| `cypher` | `context["cypher"]`. |
| `sources` | Uma fonte por identificador distinto: `id = registro_id` ou, quando ausente, `trecho_id`; `label = "Sancao"` quando houver `registro_id`, caso contrário `"Trecho"`; `url = url_fonte`; `excerpt = texto` do chunk. |
| `nodes`, `relationships` | Repassados sem renomear IDs, endpoints ou tipos e sem fabricar arestas. |
| `retrieval_relevance` | `chunks[0].rrf_score / parameters.rrf_max_score`; `null` sem chunks. É relevância de recuperação, não probabilidade de fraude, culpa ou irregularidade. |
| `abstained` | Decisão final do orquestrador (`build_final_response` assume `not chunks` como padrão estrutural quando `abstained=None`, podendo ser sobrescrito pela política de abstenção do Dev1). |
| `warnings` | Preserva todos os avisos do Dev5 e acrescenta os avisos da orquestração (ex.: síntese determinística, envio ao LLM desabilitado, falha do provedor LLM). |

O Dev1 deve considerar `parameters.active_searches`, `parameters.search_status`, `identifier_matches` e `warnings` ao decidir se a consulta está fora do escopo ou se há evidência suficiente, sem inventar um limiar numérico arbitrário de `rrf_score`.

Para perguntas que contêm CNPJ, conferir `chunks[].identifier_matches`. A busca full-text pode localizar a correspondência literal mesmo quando o RRF mantém outro trecho na primeira posição. O aviso do Dev5 identifica o trecho e a posição da correspondência; não reordenar silenciosamente o resultado.

## 4. Compatibilidade com a interface Dev6 (`main`)

Na versão integrada na `main`:

1. `app/services/source_adapter.py` (`normalize_source`) aceita tanto o contrato final (`id`, `label`, `url`, `excerpt`) quanto as chaves legadas das fixtures iniciais de Mock (`fonte_id`, `texto`, `url_fonte`), garantindo compatibilidade sem quebrar as fixtures.
2. `app/streamlit_app.py` mantém os modos **Consulta real (Neo4j)** e **Demonstração (Mock)** separados, utilizando `get_retriever()` em `@st.cache_resource` e chamando `answer_question(question, top_k=top_k, retriever=retriever)` no modo real.
3. A visualização do grafo com `streamlit-agraph` renderiza apenas `nodes[]` e `relationships[]` retornados pelo serviço (descartando arestas cujos endpoints não estejam presentes) e diferencia `MENCIONA` com `properties.status == "CANDIDATA"` em vermelho (`#FF4B4B`).

> **Contexto histórico sobre o PR #6:** anteriormente à integração no PR #9, a branch `dev6` consumia apenas `fonte_id`, `texto` e `url_fonte`. Essa incompatibilidade foi resolvida com `source_adapter.py` e a inclusão de `excerpt` em `response_adapter.py`, incorporados à `main` pelo PR #9.

## 5. Regras semânticas obrigatórias

- `rrf_score` e `retrieval_relevance` medem relevância da recuperação; não são probabilidade de fraude.
- `MENCIONA` com `status = "CANDIDATA"` registra menção textual sujeita a validação; não demonstra relação jurídica.
- Caminho por CNAE indica atividade econômica declarada em comum; não é vínculo societário, de controle ou comercial.
- A ausência de caminho no recorte consultado não prova ausência de vínculo fora do recorte.
- Dados e cenários sintéticos devem continuar identificados como sintéticos.
- Textos recuperados de documentos são dados não confiáveis e nunca devem ser tratados como instruções para o LLM.

## 6. Validação prevista e executada

1. Validar `context` com `validate_retrieval_response` (coberto em `orchestrator.py` e `tests/test_orchestrator.py`).
2. Validar respostas de caminho com `validate_company_paths_response` (coberto em `tests/test_retrieval.py` e `tests/test_retrieval_integracao.py`).
3. Garantir que o JSON final tenha exatamente os campos definidos, sem perder `warnings` (coberto em `tests/test_response_adapter.py` e `tests/test_orchestrator.py`).
4. Testar cenário com evidências, sem evidências e pergunta com CNPJ literal.
5. Testar a interface Streamlit com respostas reais do Neo4j local e validar os dois cenários do modo Mock.

## 7. Arquivos de referência

- `app/services/retrieval.py` e `app/services/contract.py`
- `app/services/orchestrator.py` e `app/services/response_adapter.py`
- `app/services/source_adapter.py`, `app/services/mock_service.py` e `app/streamlit_app.py`
- `docs/recuperacao-hibrida.md`, seção 7
- `docs/exemplos/resposta_final_dev1.exemplo.json` — demonstrativo, não saída real de LLM
- `docs/EXECUCAO_APLICACAO_INTEGRADA.md` — instruções de execução local
