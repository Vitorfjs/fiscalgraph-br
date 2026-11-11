# FiscalGraph BR

> Projeto final da disciplina **Tendências em Ciência da Computação** — Bacharelado em Ciência da Computação, 2026.

## Objetivo

Investigar como um grafo de conhecimento pode apoiar a **rastreabilidade societária e a consulta explicável de informações públicas de compliance empresarial no Brasil**, conectando dados cadastrais do CNPJ a registros públicos de sanções quando houver identificadores confiáveis.

O sistema deve apresentar fontes, caminhos do grafo e limitações. Uma ligação societária, coincidência de nome ou registro em cadastro público **não constitui, isoladamente, prova de fraude, sonegação ou irregularidade atual**.

## Escopo inicial da Fase 1

- Definir domínio, problema, objetivo e limites do sistema.
- Documentar as fontes e o recorte inicial dos dados.
- Definir o modelo conceitual LPG (rótulos, propriedades e relacionamentos).
- Criar e testar constraints e índices no Neo4j.
- Registrar evidências reais da execução.

## Estrutura do repositório

```text
.
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── cypher/
│   ├── 01_schema_fiscalgraph.cypher
│   ├── 02_validacao_schema.cypher
│   └── 03_consultas_multi_hop.cypher
├── docs/
│   ├── modelo/
│   │   ├── Proposta_Fase1_FiscalGraph_BR.docx
│   │   └── modelo_lpg_fiscalgraph.png
│   ├── evidencias/
│   ├── CHECKLIST_FASE1.md
│   ├── DIVISAO_TAREFAS_FASE1.md
│   ├── FONTES_E_DECISOES.md
│   └── VALIDACAO_NEO4J.md
├── CONTRIBUTING.md
└── README.md
```

## Fontes planejadas

- Dados Abertos do CNPJ — Receita Federal: https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/cnpj
- CEIS/CNEP — Portal da Transparência: https://portaldatransparencia.gov.br/download-de-dados/ceis

Na Fase 1, essas são fontes planejadas. Registrem a competência, a data de acesso, o arquivo/API realmente utilizado e os campos confirmados antes de iniciar a ingestão. Não subir arquivos brutos grandes nem CPFs, credenciais ou dados pessoais desnecessários ao Git.

## Antes de considerar a Fase 1 pronta

1. Percorrer `docs/CHECKLIST_FASE1.md`.
2. Dividir responsáveis usando `docs/DIVISAO_TAREFAS_FASE1.md`.
3. Registrar decisões e fontes em `docs/FONTES_E_DECISOES.md`.
4. Executar os scripts 01 e 02 em uma instância de desenvolvimento Neo4j compatível e preencher `docs/VALIDACAO_NEO4J.md` com resultados reais.
5. Abrir Pull Requests para as contribuições e confirmar que cada integrante realizou contribuições substantivas com sua própria conta.

## Status

- [ ] Escopo validado pelo grupo
- [ ] Fontes e recorte documentados
- [ ] Modelo conceitual revisado
- [ ] Schema executado e validado no Neo4j
- [ ] Evidências registradas
- [ ] Pull Requests revisados e integrados

Consulte o documento de proposta em `docs/modelo/`. O conteúdo é uma base inicial de trabalho e deve ser revisado, executado e validado pelo grupo — não representa comprovação de execução do Neo4j.


## 🖥️ Como Executar a Interface (Modo Mock - Módulo Dev6)

Para testar a interface de visualização sem depender da integração final e do
pipeline completo do Neo4j, utilize os dados sintéticos:

1. Crie e ative um ambiente virtual:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

3. Inicie a aplicação Streamlit:
    ```bash
    streamlit run app/streamlit_app.py
    ```