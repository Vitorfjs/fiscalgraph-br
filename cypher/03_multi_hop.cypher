// FiscalGraph BR — dev5: caminho mínimo (shortestPath) entre empresas do recorte.
// Neo4j 5 Community, Cypher puro: não requer Graph Data Science (GDS).
// Execute um comando por vez no Neo4j Browser (ou o arquivo inteiro com cypher-shell -f).
//
// Por que o tipo de relacionamento é sempre filtrado:
// todo nó canônico tem (n)-[:ORIGINADO_DE]->(:Fonte). Sem filtro, o caminho mínimo entre quaisquer
// duas empresas é Empresa -> Fonte <- Empresa (2 saltos), que só diz "vieram do mesmo arquivo"
// (consulta C). Por isso ORIGINADO_DE fica fora dos percursos.
//
// Interpretação: um caminho no grafo é um fato estrutural dos dados publicados, não prova de
// vínculo jurídico, fraude ou responsabilidade. CNAE compartilhado significa apenas a mesma
// classificação de atividade econômica.

// Parâmetros: cnpj_basico REAIS do recorte canônico (data/processed/canonical/empresas.csv),
// escolhidos a partir da varredura D. 00356328 = CONSTRUTORA ZAG LTDA; 01340937 = GALVAO ENGENHARIA S/A.
:param cnpj_a => '00356328';
:param cnpj_b => '01340937';

// A. Caminho societário: (Empresa A)<-[:PARTICIPA_DE]-(Socio)-[:PARTICIPA_DE]->(Empresa B).
// Resultado no recorte: VAZIO (0 linhas; e 0 dos 153 pares na varredura D restrita a PARTICIPA_DE).
// Motivo: socio_id tem escopo por empresa (docs/modelagem-lpg.md, seção 6.3) e o recorte não traz
// identificador que ligue a mesma pessoa a duas empresas. Nome nunca é usado para criar identidade.
MATCH (a:Empresa {cnpj_basico: $cnpj_a}), (b:Empresa {cnpj_basico: $cnpj_b})
WHERE a <> b
MATCH p = shortestPath((a)-[:PARTICIPA_DE*..6]-(b))
RETURN p, length(p) AS quantidade_relacionamentos;

// B. Caminho estrutural mínimo, sem ORIGINADO_DE.
// Resultado no recorte (4 relacionamentos):
// (Empresa:00356328)-[:POSSUI_ESTABELECIMENTO]->(Estabelecimento:00356328000145)-[:EXERCE_CNAE]->
// (CNAE:4211101 "Construção de rodovias e ferrovias")<-[:EXERCE_CNAE]-(Estabelecimento:01340937000179)
// <-[:POSSUI_ESTABELECIMENTO]-(Empresa:01340937)
MATCH (a:Empresa {cnpj_basico: $cnpj_a}), (b:Empresa {cnpj_basico: $cnpj_b})
WHERE a <> b
MATCH p = shortestPath(
  (a)-[:PARTICIPA_DE|POSSUI_ESTABELECIMENTO|EXERCE_CNAE|APLICADA_A|EXTRATO_DE|MENCIONA*..6]-(b)
)
RETURN p,
       [n IN nodes(p) | head(labels(n)) + ':' +
          coalesce(n.cnpj, n.cnpj_basico, n.codigo, n.socio_id, n.registro_id, n.trecho_id)] AS nos,
       [r IN relationships(p) | type(r)] AS relacionamentos,
       length(p) AS quantidade_relacionamentos;

// C. Contraprova: sem filtro de tipo, o caminho "mínimo" passa pela Fonte e não tem significado.
// Resultado no recorte: Empresa:00356328 -[:ORIGINADO_DE]-> Fonte:F-RFB-CNPJ <-[:ORIGINADO_DE]- Empresa:01340937.
MATCH (a:Empresa {cnpj_basico: $cnpj_a}), (b:Empresa {cnpj_basico: $cnpj_b})
WHERE a <> b
MATCH p = shortestPath((a)-[*..6]-(b))
RETURN [n IN nodes(p) | head(labels(n)) + ':' + coalesce(n.cnpj_basico, n.fonte_id, n.cnpj, n.codigo)] AS nos,
       [r IN relationships(p) | type(r)] AS relacionamentos,
       length(p) AS quantidade_relacionamentos;

// D. Varredura de todos os pares de empresas com caminho estrutural (origem dos parâmetros acima).
// Resultado no recorte: 14 pares; 8 com 4 relacionamentos (um CNAE em comum) e 6 com 6 (dois CNAEs).
MATCH (a:Empresa), (b:Empresa)
WHERE a.cnpj_basico < b.cnpj_basico
MATCH p = shortestPath(
  (a)-[:PARTICIPA_DE|POSSUI_ESTABELECIMENTO|EXERCE_CNAE|APLICADA_A|EXTRATO_DE|MENCIONA*..6]-(b)
)
RETURN a.cnpj_basico AS empresa_a,
       b.cnpj_basico AS empresa_b,
       length(p) AS quantidade_relacionamentos,
       [n IN nodes(p) WHERE n:CNAE | n.codigo] AS cnaes_intermediarios
ORDER BY quantidade_relacionamentos, empresa_a, empresa_b;

// E. CENÁRIO SINTÉTICO — NÃO FAZ PARTE DO RECORTE.
// Ilustra o padrão Empresa A <- Socio -> Empresa B, ausente nos dados reais (consulta A).
// Os nós levam o rótulo extra :Sintetico, sintetico = true e IDs com hífen ("SINT-..."), que não são
// CNPJ válido e não colidem com dados reais. Uma única instrução cria, consulta e apaga: se qualquer
// parte falhar, a transação inteira é desfeita. tests/test_multi_hop_sintetico.py executa este mesmo
// bloco dentro de uma transação com rollback.
// <cenario-sintetico>
CREATE (a:Empresa:Sintetico {cnpj_basico: 'SINT-EMP-A', razao_social: 'EMPRESA SINTETICA A', sintetico: true}),
       (b:Empresa:Sintetico {cnpj_basico: 'SINT-EMP-B', razao_social: 'EMPRESA SINTETICA B', sintetico: true}),
       (s:Socio:Sintetico {socio_id: 'SINT-SOC-1', tipo_pessoa: 'PESSOA JURIDICA', sintetico: true}),
       (s)-[:PARTICIPA_DE {registro_origem: 'SINTETICO'}]->(a),
       (s)-[:PARTICIPA_DE {registro_origem: 'SINTETICO'}]->(b)
WITH a, b, s
MATCH p = shortestPath((a)-[:PARTICIPA_DE*..6]-(b))
WITH a, b, s,
     [n IN nodes(p) | head(labels(n)) + ':' + coalesce(n.cnpj_basico, n.socio_id)] AS nos,
     [r IN relationships(p) | type(r)] AS relacionamentos,
     length(p) AS quantidade_relacionamentos
DETACH DELETE a, b, s
RETURN 'SINTETICO' AS cenario, nos, relacionamentos, quantidade_relacionamentos;
// </cenario-sintetico>

// E2. Conferência de limpeza do cenário sintético. Esperado: 0.
MATCH (n:Sintetico) RETURN count(n) AS nos_sinteticos_restantes;
