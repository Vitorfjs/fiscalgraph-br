# Checklist de Fechamento e Reprodução — FiscalGraph BR

Este documento organiza a última validação e a entrega acadêmica. Não marque como concluída uma etapa apenas porque existe um script ou um teste correspondente.

## 1. Estado já documentado

- [x] PR #10 integrado em main (merge commit 5dc7269e330d90175a7cf78d09e6543d4356bc6d).
- [x] Workflows do PR #10 aprovados: runs 43327963350 e 43327963370.
- [x] Workflows do PR #11 aprovados: runs 43436377286 e 43436377182.
- [x] Suíte automatizada do CI: 181 testes na referência PR #11 (run `43436377286`) e 203 testes aprovados no fechamento final (run `43479179573`).
- [x] Rodada manual reportada pelo grupo: 8/8 cenários aprovados.
- [x] Regressão para colisão lexical João Pessoa coberta por teste unitário e integração em Neo4j real do CI.
- [x] Benchmark registrado com a conclusão desfavorável ao RRF frente ao Full-Text neste dataset.
- [x] Limitações metodológicas e de dados registradas.

## 2. Reprodução em instalação limpa

Faça esta etapa em clone atualizado de main e, preferencialmente, em um volume Docker novo. Não apague o volume de desenvolvimento habitual.

### 2.1. Obter o projeto e preparar Python

~~~bash
git clone https://github.com/Vitorfjs/fiscalgraph-br.git
cd fiscalgraph-br
git checkout main
git pull --ff-only

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch
python -m pip install -r requirements.txt -r requirements-ci.txt
~~~

No Windows, crie e ative o ambiente com py -3.11 -m venv .venv e .venv\Scripts\Activate.ps1.

### 2.2. Configurar Neo4j

~~~bash
cp .env.example .env
~~~

Edite o arquivo .env e substitua NEO4J_PASSWORD por uma senha local forte. Não versione .env nem compartilhe a senha em capturas de tela.

Para manter seu volume habitual isolado, use um nome de projeto Compose separado:

~~~bash
docker compose -p fiscalgraph-validation --env-file .env -f infra/compose.yaml up -d
python scripts/check_neo4j.py
~~~

### 2.3. Validar e carregar os dados

~~~bash
python scripts/validate_canonical_data.py
python scripts/validate_canonical_relations.py
python scripts/load_canonical_data.py --dry-run
python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl --dry-run

python scripts/apply_schema.py
python scripts/load_canonical_data.py
python pipeline/text_to_graph/load_graph.py --input data/processed/trechos.jsonl
python scripts/generate_embeddings.py --dry-run
python scripts/generate_embeddings.py --batch-size 32
~~~

Depois, confira cypher/02_validacao_schema.cypher, SHOW CONSTRAINTS e SHOW INDEXES. Para a amostra versionada, os resultados históricos registrados são 210 nós, 405 relacionamentos, 54/54 trechos com embedding e índices ONLINE; a execução nova deve confirmar esses números em vez de presumir que são verdadeiros.

### 2.4. Testar a aplicação e casos essenciais

~~~bash
python -m compileall -q app pipeline scripts tests
python -m unittest discover -s tests -v
python scripts/evaluate_retrieval_benchmark.py --k 5
streamlit run app/streamlit_app.py
~~~

Na interface em modo Consulta real (Neo4j), verificar:

1. "Quais empresas foram declaradas inidôneas no CEIS?" — deve apresentar evidências e fontes pertinentes ao recorte.
2. "Qual a situação do CNPJ 01.340.937/0001-79?" — verificar correspondência literal, fontes e aviso de priorização quando aplicável.
3. "Qual a situação do CNPJ 99.999.999/0001-99?" — deve abster-se, sem fontes ou subgrafo.
4. "Qual a previsão do tempo para João Pessoa amanhã ou a receita de bolo de milho?" — deve abster-se apesar de eventual colisão Full-Text; sem fontes nem subgrafo.

Verifique também Demonstração (Mock) nos modos sucesso e abstenção. Não misture fixtures sintéticas com resultados da consulta real.

### 2.5. Registrar a reprodução local

Preencha com valores observados, sem copiar os valores históricos:

| Campo | Valor desta execução |
| --- | --- |
| Responsável(is) | |
| Data/hora e fuso | |
| Sistema operacional | |
| Python (python --version) | |
| Neo4j (CALL dbms.components()) | |
| Commit (git rev-parse HEAD) | |
| Testes (unittest ...) | |
| Nós / relacionamentos | |
| Embeddings / índices | |
| Resultado dos quatro casos da interface | |
| Link/pasta das capturas de tela | |

Salve a saída de python -m pip freeze como evidência do ambiente efetivamente usado, por exemplo docs/evidencias/ambiente-local-freeze.txt. Os arquivos requirements*.txt atuais declaram versões mínimas; eles não fixam todas as versões transitivas como um lockfile.

## 3. Preparação da entrega acadêmica

- [x] Fonte do artigo técnico em LaTeX no template SBC adicionada em `artigo/` (`main.tex`, `referencias.bib` e arquivos de estilo).
- [x] Workflow de compilação do artigo SBC aprovado; PDF de 7 páginas gerado no run `43479179639` (artefato `artigo-fiscalgraph-br-sbc`).
- [x] Slides de apresentação técnica gerados em PPTX e PDF no ambiente de trabalho desta sessão; identificação do grupo ainda é placeholder.
- [x] Geração opcional de Cypher por LLM integrada à interface com opt-in, validação read-only, `EXPLAIN` e limite de linhas; suíte automatizada aprovada. Teste com provedor real continua dependente de credenciais do grupo.
- [x] Resolução nominal conservadora adicionada para nomes normalizados com correspondência única; colisões não geram arestas e o NER continua opcional.
- [x] Interface passou a exibir nível heurístico de sustentação documental com critérios e ressalva; não é confiança estatística.
- [ ] Conferir o enunciado e a rubrica da disciplina; ajustar o documento somente quando a rubrica justificar.
- [ ] Conferir se o relatório identifica problema, objetivos, domínio, fontes, modelagem LPG, arquitetura, implementação, método de avaliação, resultados e limitações.
- [ ] Anexar diagrama conceitual e dicionário de dados.
- [x] Benchmark, evidências históricas de CI e validação manual reportada pelo grupo documentados.
- [ ] Anexar capturas reais da execução atual após a reprodução limpa.
- [ ] Incluir capturas reais da interface: consulta com evidências, abstenção sem subgrafo, grafo com aresta candidata e Mock.
- [ ] Preencher nomes dos integrantes, disciplina, docente, instituição e data; não deixar placeholders.
- [ ] Conferir referências das bases públicas e explicar o serviço intermediário usado para o cadastro CNPJ.
- [ ] Revisar a linguagem para não afirmar fraude, culpa ou vínculo jurídico com base em coincidência, menção candidata ou score de recuperação.

## 4. Divisão interna do grupo

Preencham entre os integrantes antes da apresentação:

| Frente | Responsável | Entrega |
| --- | --- | --- |
| Reprodução limpa e capturas | | Evidência local atual |
| Relatório e referências | | Documento final |
| Slides e fala | | Apresentação sincronizada |
| Demonstração técnica | | Interface e plano B |
| Revisão da rubrica/submissão | | Pacote de entrega |

## 5. Critério de encerramento

A branch de fechamento reúne as extensões de software e os artefatos acadêmicos iniciais. Não considere o fechamento técnico concluído antes de a CI desta branch aprovar testes e compilação do artigo. A entrega acadêmica só deve ser considerada concluída depois da reprodução limpa, do preenchimento da identificação dos integrantes, da revisão do artigo e dos slides com base na rubrica real da disciplina, e da confirmação de acesso do professor ao repositório se ele permanecer privado.
