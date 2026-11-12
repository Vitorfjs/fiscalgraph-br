# Política de Abstenção e Orquestração — FiscalGraph BR (Dev1)

Este documento define as regras verificáveis implementadas em `app/services/orchestrator.py` (`evaluate_abstention_policy`, `_verify_llm_grounding` e `answer_question`) para decidir entre responder com evidências, apresentar limitações ou abster-se.

> **Princípio fundamental:** `rrf_score` e `retrieval_relevance` **não** são interpretados como probabilidade jurídica, grau de certeza nem limiar numérico arbitrário de abstenção.

---

## 1. Regras Verificáveis da Política de Abstenção

| Cenário observado | Condição verificável sobre o contrato Dev5 | Decisão (`abstained`) | Comportamento esperado |
| --- | --- | --- | --- |
| **Índices indisponíveis sem trechos** | `not chunks` e `search_status.vector == "indisponivel"` e `search_status.fulltext == "indisponivel"` | `true` | Abster-se, limpar `sources`/`nodes`/`relationships` e registrar indisponibilidade técnica em `warnings`. |
| **Sem trechos recuperados** | `not chunks` | `true` | Abster-se e informar que não há trechos no recorte consultado (sem afirmar inexistência fora do recorte). |
| **CNPJ informado sem correspondência** | `query_identifiers` não vazio e nenhum CNPJ pedido aparece em `chunks[].identifier_matches` nem em `Estabelecimento.cnpj` / `Sancao.cnpj_sancionado` de `nodes[]` | `true` | Abster-se, não exibir registros de outros CNPJs como evidência e registrar o CNPJ não encontrado em `warnings`. |
| **Pergunta sem âncora de domínio** | Sem `query_identifiers` e `_has_domain_anchor(query) == False`, independentemente de a busca Full-Text ou vetorial ter retornado trechos | `true` | Abster-se e limpar `sources`/`nodes`/`relationships`; resultados obtidos apenas por coincidência lexical não validam a pergunta. |
| **Colisão lexical (ex.: João Pessoa / pessoa jurídica)** | A pergunta não contém âncora de domínio; o Full-Text retorna trechos que contêm palavras coincidentes | `true` | Abster-se, descartar fontes e subgrafo recuperados e registrar a colisão lexical em `warnings`. |
| **Pergunta com âncora de domínio** | Termos ou identificadores reconhecidos na própria pergunta, com evidências recuperadas | `false` ou outra regra aplicável | Avaliar as evidências e manter avisos de busca parcial; a existência de resultados não basta, por si só, para provar pertinência. |
| **Busca parcialmente indisponível** | `vector == "indisponivel"` ou `fulltext == "indisponivel"` com trechos válidos na outra modalidade | `false` | Apresentar as evidências recuperadas e incluir aviso explícito de cobertura parcial em `warnings`. |
| **Evidência relacionada apenas semanticamente** | `fulltext == "sem_resultados"`, `active_searches == ["vector"]`, com termos/âncora do domínio presentes | `false` | Apresentar o que foi encontrado e registrar explicitamente em `warnings` que não houve confirmação lexical nos trechos (evidência insuficiente para conclusão definitiva). |
| **Pergunta com CNPJ encontrado em posição ≥ 2** | `query_identifiers` encontrado em `identifier_matches` | `false` | Responder preservando `sources` e destacar primeiro o trecho com correspondência literal de CNPJ na síntese determinística. |
| **Evidências suficientes** | Trechos recuperados válidos sem violação das regras acima | `false` | Responder exclusivamente com base nos trechos recuperados, preservando avisos de `MENCIONA (CANDIDATA)` quando presentes. |

---

## 2. Validação de Escopo sem Circularidade

A função `_has_domain_anchor(query)` considera somente termos e identificadores presentes na pergunta original. Ela não recebe nem consulta nós, nomes de empresas, descrições ou trechos retornados pelo mecanismo de recuperação.

Essa separação impede que um falso positivo do Full-Text valide a própria pergunta. Por exemplo, a palavra "Pessoa" em "João Pessoa" não pode ser tratada como âncora por causa da expressão "pessoa jurídica" em um documento retornado.

A pergunta "Qual a previsão do tempo para João Pessoa amanhã ou a receita de bolo de milho?" deve resultar em abstenção mesmo quando a busca lexical retorna trechos. O teste unitário simula essa colisão; o teste de integração exige que o Neo4j reproduza um resultado Full-Text antes de verificar a abstenção do orquestrador.

## 3. Modo Determinístico e LLM Opcional (`_llm_answer`)

- **Modo padrão (sem LLM ou `LLM_SEND_EVIDENCE != "true"`):** o sistema gera síntese determinística transparente (`_deterministic_answer`) e registra explicitamente em `warnings` que não houve geração por LLM.
- **Ativação externa (opt-in):** exige `LLM_CHAT_COMPLETIONS_URL`, `LLM_API_KEY`, `LLM_MODEL` e `LLM_SEND_EVIDENCE=true`. Os dados enviados pelo `_evidence_payload` minimizam propriedades de pessoas naturais.
- **Proteção contra injeção em documentos:** o `system_prompt` instrui o modelo a tratar o texto dos trechos como dado não confiável, nunca como instrução.
- **Fallback automático:** timeouts, erros HTTP/rede, respostas vazias ou JSON malformado acionam o fallback determinístico com aviso claro, sem expor chaves ou segredos.

---

## 4. Verificação de Citações e Rastreabilidade (`_verify_llm_grounding`)

Quando o LLM retorna uma resposta:

1. O validador extrai todos os identificadores de registro (`CEIS-...`, `CNEP-...`, `REG-...`, `TR-...`, `SOC-...`, `F-...`) e CNPJs de 14 posições citados na resposta.
2. Compara com o conjunto de identificadores efetivamente presentes nos `chunks`, `nodes` e `query_identifiers` da consulta.
3. **Identificador inventado:** se o LLM citar qualquer identificador ou CNPJ ausente do contexto recuperado, a resposta é **rejeitada**, substituída pela síntese determinística e acompanhada de aviso em `warnings`.
4. **Ausência de citação explícita:** se a resposta não citar nenhum `registro_id`/`trecho_id` recuperado, é adicionado um aviso recomendando conferência direta das fontes listadas.

---

## 5. Exemplos Reais Verificados (Neo4j Local — 2026-11-11)

- **Domínio com evidências (`"Quais empresas foram declaradas inidôneas para licitar com a administração pública?"`):** `abstained=false`, 5 fontes rastreáveis, 27 nós, 26 relacionamentos, síntese determinística sinalizada em `warnings`.
- **CNPJ literal (`"trecho que cita o CNPJ 01.340.937/0001-79"`):** `abstained=false`, 5 fontes, síntese determinística priorizando `CEIS-289814` (`[Correspondência literal de CNPJ]`) e preservando o aviso do Dev5 sobre a 2ª posição no RRF.
- **CNPJ ausente do recorte (`"Quais sanções existem para o CNPJ 99.999.999/0001-99?"`):** `abstained=true`, `sources=[]`, `nodes=[]`, `relationships=[]`, explicando o limite da amostra de 18 empresas.
- **Fora do domínio (`"receita de bolo de chocolate"`):** `abstained=true`, `sources=[]`, `nodes=[]`, `relationships=[]`, `LLM` não chamado, explicando a abstenção por ausência de termos do domínio e de correspondência lexical.
