# Roteiro de Demonstração e Apresentação — FiscalGraph BR

**Duração sugerida:** 8 minutos  
**Objetivo:** demonstrar o fluxo ponta a ponta, explicar por que o grafo agrega valor e apresentar os resultados sem esconder limitações.

## Antes de iniciar (não contabilizar)

1. Atualizar para main e confirmar o commit que será apresentado.
2. Iniciar Neo4j e confirmar conexão:

~~~bash
docker compose --env-file .env -f infra/compose.yaml up -d
python scripts/check_neo4j.py
~~~

3. Abrir a interface:

~~~bash
streamlit run app/streamlit_app.py
~~~

4. Deixar o benchmark e o relatório acessíveis em outras abas.
5. Confirmar que a opção selecionada é Consulta real (Neo4j). Não apresentar resultados do Mock como se viessem do banco real.

## 0:00–1:00 — Problema e proposta

**Fala sugerida**

> O FiscalGraph BR é um protótipo acadêmico de GraphRAG voltado à exploração explicável de dados públicos empresariais e registros de sanções. A proposta é combinar recuperação textual com um grafo LPG no Neo4j para apresentar evidências, fontes e relações que ajudem a contextualizar uma consulta. O sistema não determina fraude nem substitui auditoria ou análise jurídica.

**Mostrar**

- Título e aviso metodológico da aplicação.
- Status de conexão com Neo4j.
- Contagens atuais de nós e relacionamentos, somente se confirmadas nessa execução.

## 1:00–2:30 — Arquitetura e modelagem

**Fala sugerida**

> Os dados são organizados em entidades como Empresa, Estabelecimento, Sócio, CNAE, Sanção, Fonte e Trecho. As relações registram participação societária, estabelecimentos, atividades econômicas, sanções e proveniência. Os trechos textuais mantêm ligação com a sanção e a fonte de origem. Isso permite percorrer contexto estruturado e evidência documental, em vez de retornar apenas um texto isolado.

**Mostrar**

- Diagrama LPG.
- Na interface, apontar fontes/trechos e consulta Cypher.
- Destacar MENCIONA (CANDIDATA): é menção textual pendente de validação, não uma relação jurídica comprovada.

## 2:30–4:00 — Consulta real com evidências

**Pergunta para executar**

"Quais empresas foram declaradas inidôneas no CEIS?"

**Fala sugerida**

> Nesta consulta, a aplicação recupera trechos relacionados ao tema e apresenta a resposta junto das fontes e dos caminhos no grafo retornados. O ponto importante é a rastreabilidade: podemos inspecionar o trecho, sua origem e a consulta usada, em vez de aceitar uma resposta sem evidência.

**Mostrar**

- Resposta e avisos.
- Fontes e trechos expandidos.
- Subgrafo retornado.
- Consulta Cypher, se o tempo permitir.

Os números de fontes, nós e relações podem variar conforme o banco e a consulta. Não decorar contagens antigas; use os valores mostrados na execução ao vivo.

## 4:00–5:00 — Correspondência literal de CNPJ

**Pergunta para executar**

"Qual a situação do CNPJ 01.340.937/0001-79?"

**Fala sugerida**

> Identificadores literais exigem cuidado especial em recuperação semântica. Por isso, o sistema verifica correspondências de CNPJ e pode sinalizar ou priorizar o identificador encontrado. O aviso deixa explícito quando a correspondência literal precisou ser considerada além da posição original no ranking.

**Mostrar**

- Trecho associado ao CNPJ.
- Fonte original.
- Aviso de correspondência literal, quando exibido.
- Relações candidatas em estilo visual diferente.

## 5:00–6:15 — Abstenção e controle de escopo

**Pergunta para executar**

"Qual a previsão do tempo para João Pessoa amanhã ou a receita de bolo de milho?"

**Fala sugerida**

> Uma recuperação lexical pode encontrar palavras que também aparecem em documentos do domínio, sem que a pergunta realmente seja sobre compliance. O sistema precisa reconhecer esse risco. Neste caso, mesmo que o Full-Text retorne coincidências, a pergunta não tem âncora verificável do domínio e a aplicação se abstém, sem exibir fontes ou subgrafo como se fossem relevantes.

**Mostrar**

- Mensagem de abstenção.
- Ausência de fontes e subgrafo.
- Explicar que esse comportamento é coberto por teste unitário, integração em Neo4j no CI e validação manual reportada pelo grupo.

Se houver tempo, testar também:

"Qual a situação do CNPJ 99.999.999/0001-99?"

Reforçar que ausência no recorte não prova inexistência na base pública nacional.

## 6:15–7:00 — Modo Mock

**Fala sugerida**

> O modo Mock desacopla a demonstração do banco e usa fixtures sintéticas para mostrar o fluxo de sucesso e o fluxo de abstenção. Ele serve para testes e apresentação quando o Neo4j não está disponível, mas não representa uma consulta real.

**Mostrar**

- Alternar para Demonstração (Mock).
- Demonstrar sucesso e depois abstenção.
- Apontar o aviso de conteúdo sintético.

## 7:00–8:00 — Resultados, limitações e encerramento

**Fala sugerida**

> O benchmark comparou recuperação vetorial, Full-Text e RRF em 16 consultas positivas, além de casos de abstenção. Neste conjunto, o Full-Text puro obteve os melhores resultados agregados; o RRF melhorou sobre a busca vetorial pura, mas não superou o Full-Text. Isso é importante: a avaliação não sustenta afirmar que a abordagem híbrida venceu. A amostra é pequena, com 54 trechos e 18 empresas, então os resultados não devem ser generalizados. O protótipo prioriza rastreabilidade, explicitação de incerteza e abstenção segura.

**Mostrar**

- Tabela de benchmark.
- Limitações: snapshot pequeno, dependência de fonte intermediária para CNPJ, ausência de inferência jurídica e relações MENCIONA candidatas.
- Status da suíte automatizada com referência ao run de CI 43327963350 (179 testes) e à validação manual reportada (8/8 cenários).

## Plano B para a demonstração

| Problema | Alternativa |
| --- | --- |
| Neo4j não inicia ou conexão falha | Abrir o modo Mock e deixar claro que as fixtures são sintéticas |
| Modelo de embeddings ainda está baixando | Não improvisar números; usar evidências previamente geradas e sinalizar que a consulta real depende do modelo local |
| Interface demora ou consulta retorna resultado diferente | Não afirmar contagens fixas; mostrar o benchmark/documentação e explicar que o subgrafo depende da consulta |
| Pergunta fora de escopo retorna coincidências lexicais | Usar a regressão João Pessoa e verificar se o commit apresentado é o integrado e testado |

## Perguntas prováveis da banca

**Por que usar um grafo, em vez de apenas uma base relacional?**  
O grafo representa explicitamente entidades e relações e permite navegar por caminhos multi-hop e proveniência. A escolha é útil para explicar como evidências e entidades se conectam; não significa que um grafo seja sempre superior a um modelo relacional.

**A relação MENCIONA prova ligação entre empresas?**  
Não. Ela registra uma ocorrência textual de CNPJ e permanece com estado CANDIDATA. Exige validação humana e não deve ser interpretada como vínculo jurídico.

**O sistema detecta fraude?**  
Não. Ele organiza e recupera evidências públicas para análise preliminar. Scores medem relevância de recuperação, não probabilidade de fraude nem responsabilidade.

**Por que o Full-Text superou o RRF?**  
O corpus é pequeno e contém muitos termos legais, números de processo, CNPJs e siglas. A correspondência lexical foi muito eficaz. A fusão RRF melhorou a recuperação vetorial, mas termos genéricos compartilhados também elevaram trechos menos específicos. O resultado vale para o dataset avaliado.

**O que significa não encontrar um CNPJ?**  
Significa que não foi encontrada evidência correspondente no recorte local. Não significa inexistência de registro em toda a base pública nacional.


## Demonstração adicional: planejamento LLM-to-Cypher

O recurso `app/services/nl_cypher.py` planeja consultas a partir de uma intenção JSON
e compila somente templates previamente permitidos, com parâmetros vinculados e
transação Neo4j somente leitura. O recurso permanece desligado por padrão. Para
demonstrá-lo ao vivo, o grupo precisa configurar um endpoint compatível, autorizar o
envio da pergunta ao provedor e habilitar explicitamente as duas variáveis de ambiente.
Sem essas condições, demonstre a recuperação híbrida já validada e informe que a
integração externa não foi testada.
