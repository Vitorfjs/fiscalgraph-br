# Contrato de integração final — FiscalGraph BR

**Revisão:** 2026-11-11  
**Base técnica:** branch `dev5`  
**Objetivo:** registrar o formato de integração entre recuperação (Dev5), orquestração/resposta (Dev1) e interface (Dev6), evitando adaptações implícitas entre módulos.

## 1. Estado verificado do repositório

| Módulo | Estado observado | Consequência |
| --- | --- | --- |
| Dev5 — recuperação híbrida | Serviço, validadores, testes unitários e testes de integração presentes na branch `dev5`. | Pode ser consumido por Dev1. |
| Dev1 — orquestração e resposta | A branch `dev1` examinada contém somente a tela Streamlit inicial; não foi encontrado serviço de orquestração, chamada a LLM ou montagem de resposta final. | A integração funcional Dev1–Dev5 ainda não pode ser validada contra uma implementação real. |
| Dev6 — interface | Branch `dev6` com interface em modo mock; PR #6 aberto. | A tela demonstra apresentação de fixtures, não execução do fluxo real. |

Esta documentação define o contrato esperado; ela não afirma que os módulos Dev1 e Dev6 já estejam integrados.

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

O Dev5 retorna evidências; não redige a resposta em linguagem natural nem decide uma política completa de abstenção.

## 3. Formato da resposta final do Dev1

O formato final documentado é:

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

Regras de mapeamento:

| Campo final | Origem/regra |
| --- | --- |
| `answer` | Produzido pelo Dev1 a partir dos trechos e das evidências; não copiar o texto demonstrativo do exemplo. |
| `cypher` | `context["cypher"]`. |
| `sources` | Uma fonte por identificador distinto: `id = registro_id` ou, quando ausente, `trecho_id`; `label = "Sancao"` quando houver `registro_id`, caso contrário `"Trecho"`; `url = url_fonte`; `excerpt = texto` do chunk. |
| `nodes`, `relationships` | Repassar sem renomear IDs, endpoints ou tipos. |
| `retrieval_relevance` | Sugestão já implementada em `example_final_response`: `chunks[0].rrf_score / parameters.rrf_max_score`; `null` sem chunks. É relevância de recuperação, não probabilidade de fraude, culpa ou irregularidade. |
| `abstained` | Decisão final do Dev1. O exemplo do Dev5 usa `not chunks` apenas como mapeamento estrutural; não substitui a política de escopo/suficiência que o Dev1 deve implementar. |
| `warnings` | Preservar todos os avisos do Dev5 e acrescentar avisos produzidos pelo Dev1, sem apagar os anteriores. |

O Dev1 deve considerar `parameters.active_searches`, `parameters.search_status` e `warnings` ao decidir se a consulta está fora do escopo ou se há evidência suficiente. Não há um limiar numérico de abstenção definido por esta especificação; não inventar um silenciosamente.

Para perguntas que contêm CNPJ, conferir `chunks[].identifier_matches`. A busca full-text pode localizar a correspondência literal mesmo quando o RRF mantém outro trecho na primeira posição. O aviso do Dev5 identifica o trecho e a posição da correspondência; não reordenar silenciosamente o resultado.

## 4. Compatibilidade com a interface Dev6

A interface atualmente existente na branch `dev6` foi implementada com fixtures mock e espera, dentro de `sources[]`, as propriedades:

- `fonte_id`
- `texto`
- `url_fonte`

Ela também tenta exibir esses campos diretamente. Isso **não corresponde** ao contrato final acima, que define `sources[]` como `id`, `label`, `url` e `excerpt`. Portanto, a substituição do mock por uma resposta real sem ajustar o consumidor fará a tela exibir valores ausentes (por exemplo, `N/A` e "Sem texto disponível") e não mostrará o link pela chave esperada.

Decisão de integração:

1. Manter o contrato final documentado (`id`, `label`, `url`) como formato de `sources[]`.
2. Ajustar o renderer/adaptador do Dev6 para ler essas chaves.
3. Se a interface precisar exibir o trecho textual, consumir `sources[].excerpt`, campo textual explicitamente incluído no contrato final; não tratar `sources[]` como se fosse `chunks[]` nem duplicar texto sob nomes diferentes sem acordo.
4. Manter `nodes[]` e `relationships[]` na estrutura do grafo devolvida pelo Dev5. Não fabricar arestas no frontend.
5. Renderizar `MENCIONA` com `properties.status = "CANDIDATA"` como menção candidata, nunca como vínculo confirmado.

A branch `dev6` e o PR #6 precisam ser atualizados pelo responsável da interface antes da integração real. Esta branch Dev5 registra o contrato e a incompatibilidade; não altera a branch Dev6.

## 5. Regras semânticas obrigatórias

- `rrf_score` e `retrieval_relevance` medem relevância da recuperação; não são probabilidade de fraude.
- `MENCIONA` com `status = "CANDIDATA"` registra menção textual sujeita a validação; não demonstra relação jurídica.
- Caminho por CNAE indica atividade econômica declarada em comum; não é vínculo societário, de controle ou comercial.
- A ausência de caminho no recorte consultado não prova ausência de vínculo fora do recorte.
- Dados e cenários sintéticos devem continuar identificados como sintéticos.

## 6. Validação prevista na integração

1. Validar `context` com `validate_retrieval_response`.
2. Validar respostas de caminho com `validate_company_paths_response`.
3. Garantir que o JSON final tenha exatamente os campos definidos, sem perder `warnings`.
4. Testar cenário com evidências, sem evidências e pergunta com CNPJ literal.
5. Testar o renderer Dev6 com a resposta final real, não apenas com fixtures.
6. Confirmar que `sources[]` usa as chaves acordadas e que a visualização não cria relacionamentos inexistentes.

## 7. Arquivos de referência

- `app/services/retrieval.py`
- `app/services/contract.py`
- `docs/recuperacao-hibrida.md`, seção 7
- `docs/exemplos/resposta_final_dev1.exemplo.json` — demonstrativo, não saída real de LLM
- PR #6 — interface Dev6 em modo mock
