# Validação Manual — Etapa 4 da Interface Streamlit (dev5)

- **Projeto:** FiscalGraph BR
- **Branch validada:** `dev5`
- **Data informada no relatório:** 2026-11-12
- **Conjunto de evidências:** `Testes/Testes 2/`
- **Resultado informado:** **8/8 cenários aprovados**

Este registro consolida o relatório técnico de validação manual apresentado pelo grupo. As capturas de tela e consultas Cypher permanecem referenciadas no conjunto de evidências indicado acima; este arquivo registra os resultados e observações descritos no relatório recebido.

## Resumo dos cenários

| # | Cenário | Resultado | Evidência principal |
|---:|---|---|---|
| 1 | Mock — resposta completa | Aprovado | Fixture identificada como sintética; resposta, fontes, Cypher, relevância 0.820 e subgrafo com 4 nós, 3 arestas e 1 menção candidata. |
| 2 | Mock — abstenção | Aprovado | Aviso de fixture sintética, mensagem de evidência insuficiente e ausência de subgrafo. |
| 3 | Consulta real — CNPJ conhecido | Aprovado | CNPJ 01.340.937/0001-79 localizado por correspondência literal; CEIS-289814 priorizado; 5 fontes, 25 nós, 26 arestas e 2 menções candidatas. |
| 4 | Consulta real — pergunta semântica | Aprovado | Recuperação vetorial + Full-Text + RRF; 5 registros pertinentes sobre fraude à licitação/inidoneidade; 23 nós e 23 arestas. |
| 5 | Consulta real — CNPJ sem evidência | Aprovado | CNPJ 00.000.000/0001-91 sem correspondência no recorte; abstenção sem exibir sanções de terceiros ou subgrafo. |
| 6 | Consulta fora de escopo — João Pessoa / receita de bolo | Aprovado | Consulta exata sem âncora de domínio; coincidências lexicais descartadas; abstenção sem fontes nem subgrafo. |
| 7 | Grafo e relacionamentos candidatos | Aprovado | Nós/arestas do Neo4j com contadores e legenda; `MENCIONA (CANDIDATA)` em vermelho tracejado. |
| 8 | Falha de conexão | Aprovado | Neo4j parado e credenciais inválidas tratados com mensagens orientativas, sem stack trace Python bruto. |

## Evidência detalhada da regressão de escopo

Pergunta executada no cenário 6:

`Qual a previsão do tempo para João Pessoa amanhã ou a receita de bolo de milho?`

O relatório informa que o filtro de escopo identificou ausência de âncora do domínio, descartou resultados por coincidência lexical (incluindo a palavra "Pessoa") e apresentou:

- aviso: "Consulta fora do domínio/escopo verificável: não há âncora na pergunta; resultados recuperados por coincidência lexical foram descartados.";
- abstenção: a pergunta não contém termo ou identificador verificável do domínio FiscalGraph BR;
- subgrafo: nenhum subgrafo retornado.

Este cenário manual complementa os testes automatizados unitário e de integração já registrados na Parte E de `docs/validacao-neo4j.md`. A integração automatizada exige que o Full-Text retorne resultados no Neo4j temporário antes de aprovar a abstenção.

## Observações de qualidade do relatório

- O cenário 3 apresenta relevância normalizada 0.992; o cenário 4 comprova pertinência em pergunta semântica sem depender exclusivamente de um CNPJ literal.
- O cenário 5 diferencia ausência de correspondência no recorte de inexistência na base pública nacional.
- O cenário 7 mantém a distinção visual entre relações estruturais e relações candidatas; a marca `CANDIDATA` não representa vínculo jurídico confirmado.
- O cenário 8 cobre tanto indisponibilidade de rede quanto falha de autenticação.
- O relatório recebido aponta capturas duplicadas nos cenários 4 e 7; essas duplicatas não foram tratadas como cenários adicionais.

## Escopo e limite desta evidência

Este documento registra o resultado descrito no relatório de validação manual entregue pelo grupo e não substitui as capturas de tela nem os arquivos de consulta Cypher originais. O conjunto citado é `Testes/Testes 2/`. A validação automatizada de CI (179 testes, incluindo o Neo4j de CI) está documentada separadamente em `docs/validacao-neo4j.md`, Parte E.
