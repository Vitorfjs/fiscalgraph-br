# Definição do Projeto — Fiscal Graph BR

## 1. Problema

Informações sobre empresas brasileiras, seus estabelecimentos, sócios, atividades econômicas e registros públicos de sanções estão distribuídas em diferentes bases e documentos. Analisar essas informações manualmente pode dificultar a identificação de relações indiretas entre entidades e a apresentação clara das fontes que sustentam uma conclusão, especialmente quando a consulta exige conectar mais de um relacionamento.

O Fiscal Graph BR propõe um protótipo de grafo de conhecimento com GraphRAG para integrar um recorte de dados públicos empresariais e de compliance. A ferramenta deverá permitir explorar relações entre empresas, sócios, atividades econômicas e registros oficiais relevantes, respondendo a perguntas com base em evidências recuperadas do grafo e indicando os caminhos e as fontes usados. O sistema será um apoio à análise preliminar, não um mecanismo de decisão jurídica ou de comprovação automática de irregularidades.

## 2. Pergunta central

**Como a integração de dados públicos empresariais e de registros oficiais de compliance em um grafo de conhecimento pode ajudar a explorar e explicar relações entre empresas, sócios e atividades econômicas, apresentando evidências rastreáveis para apoiar uma análise preliminar?**

## 3. Objetivo geral

Projetar e desenvolver um protótipo de GraphRAG que organize dados públicos empresariais e de compliance do Brasil em um grafo de conhecimento no Neo4j, permitindo consultas relacionais e semânticas cujas respostas sejam fundamentadas em evidências e caminhos identificáveis no grafo.

## 4. Objetivos específicos

1. Identificar e documentar fontes públicas pertinentes ao domínio, registrando sua origem, seus campos relevantes e suas limitações.
2. Definir um recorte de dados reproduzível e critérios de normalização e resolução de entidades, priorizando identificadores oficiais quando disponíveis.
3. Modelar empresas, estabelecimentos, sócios, atividades econômicas e registros de compliance como nós, propriedades e relacionamentos de um grafo LPG.
4. Implementar o esquema no Neo4j com constraints e índices adequados às consultas planejadas.
5. Desenvolver um pipeline de ingestão que extraia e normalize entidades e relacionamentos dos dados selecionados, preservando a procedência das informações.
6. Implementar recuperação híbrida, combinando consultas estruturadas em Cypher e busca semântica, com capacidade de percorrer relacionamentos de múltiplos saltos.
7. Apresentar respostas apoiadas em fontes e subgrafos recuperados, permitindo ao usuário verificar os elementos que contribuíram para cada resposta.
8. Avaliar o protótipo por meio de perguntas de teste previamente definidas, verificando a relevância das informações recuperadas e a rastreabilidade das respostas.

## 5. Escopo do projeto

### Dentro do escopo

- Uso de um recorte documentado de dados públicos empresariais brasileiros, inicialmente considerando dados cadastrais do CNPJ (como empresas, estabelecimentos, QSA e CNAE) e fontes oficiais de registros de sanções ou impedimentos empresariais, desde que a disponibilidade e a compatibilidade dos campos sejam confirmadas na seleção dos datasets.
- Integração dos registros por identificadores disponíveis e documentados, sem presumir que nomes semelhantes representam a mesma entidade.
- Modelagem LPG e armazenamento no Neo4j, incluindo constraints, índices e consultas Cypher.
- Construção de um protótipo GraphRAG para responder perguntas delimitadas sobre relações empresariais e registros públicos de compliance.
- Registro da procedência dos dados e exibição dos caminhos e evidências recuperados para fundamentar as respostas.
- Avaliação acadêmica em um conjunto limitado e reproduzível de consultas de teste.

### Fora do escopo

- Carregar ou analisar integralmente toda a base nacional do CNPJ; será utilizado um recorte definido e documentado.
- Acessar dados fiscais protegidos por sigilo, declarações tributárias privadas, movimentações bancárias ou transações financeiras não disponibilizadas publicamente pelas fontes escolhidas.
- Afirmar ou concluir automaticamente que uma empresa ou pessoa praticou fraude, sonegação ou outro ilícito com base apenas em vínculos societários, CNAE, presença em cadastro público ou associação entre registros.
- Substituir auditoria, investigação, análise jurídica ou decisão de autoridade competente.
- Garantir cobertura em tempo real, implantação em ambiente produtivo ou análise completa de todas as empresas brasileiras.
- Integrar fontes adicionais, como relatórios da SEC ou datasets do Kaggle, sem decisão explícita do grupo e justificativa de compatibilidade com o escopo brasileiro.

## 6. Limitação e uso responsável

**A existência de vínculo societário, coincidência cadastral ou registro público de sanção não comprova, isoladamente, fraude, sonegação ou participação em ilícito.** O protótipo deve distinguir fatos registrados pelas fontes, relações inferidas pelo pipeline e hipóteses que necessitam de verificação humana. Sempre que possível, a resposta deverá identificar a fonte e os relacionamentos que sustentam a informação, bem como explicitar quando os dados disponíveis não forem suficientes para responder.

## 7. Premissas a validar na seleção dos datasets

- Quais arquivos e campos das fontes selecionadas estão disponíveis e atualizados para o recorte do projeto.
- Quais identificadores permitem relacionar registros com segurança, especialmente o CNPJ quando presente.
- Como tratar dados ausentes, duplicados, mudanças cadastrais e menções ambíguas.
- Se os campos selecionados sustentam cada tipo de relacionamento que será representado no grafo.

Essas premissas serão confirmadas na tarefa de pesquisa e seleção dos datasets; o presente documento define a direção do projeto, mas não substitui essa validação.
