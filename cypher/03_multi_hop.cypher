// FiscalGraph BR — dev5: caminho mínimo (shortestPath) entre empresas do recorte.
// Neo4j 5 Community, Cypher puro: não requer Graph Data Science (GDS).
// Execute um comando por vez no Neo4j Browser (ou o arquivo inteiro com cypher-shell -f).
//
// Dois tipos de caminho entre empresas, com significados diferentes:
// - SOCIETÁRIO (consulta A): Empresa <-PARTICIPA_DE- Socio -PARTICIPA_DE-> Empresa.
//   Indicaria o mesmo sócio em duas empresas. NÃO EXISTE no recorte (diagnóstico na seção E).
// - ESTRUTURAL POR CNAE (consultas B e D): Empresa -> Estabelecimento -> CNAE <- Estabelecimento <- Empresa.
//   Indica só que as empresas declaram a mesma atividade econômica. Existe no recorte (seção F).
//   Não é vínculo societário, de controle ou comercial.
//
// Por que o tipo de relacionamento é sempre filtrado:
// todo nó canônico tem (n)-[:ORIGINADO_DE]->(:Fonte). Sem filtro, o caminho mínimo entre quaisquer
// duas empresas é Empresa -> Fonte <- Empresa (2 saltos), que só diz "vieram do mesmo arquivo"
// (consulta C). Por isso ORIGINADO_DE fica fora dos percursos.
//
// Interpretação: um caminho no grafo é um fato estrutural dos dados publicados, não prova de
// vínculo jurídico, fraude ou responsabilidade.

// Parâmetros: cnpj_basico REAIS do recorte canônico (data/processed/canonical/empresas.csv),
// escolhidos a partir da varredura D. 00356328 = CONSTRUTORA ZAG LTDA; 01340937 = GALVAO ENGENHARIA S/A.
:param cnpj_a => '00356328';
:param cnpj_b => '01340937';

// A. Caminho SOCIETÁRIO: (Empresa A)<-[:PARTICIPA_DE]-(Socio)-[:PARTICIPA_DE]->(Empresa B).
// Resultado no recorte: VAZIO (0 linhas; e 0 dos 153 pares na varredura restrita a PARTICIPA_DE).
// Motivos (ver seção E): socio_id inclui o cnpj_basico da empresa, então cada nó Socio pertence a
// uma única empresa; e, no recorte, nenhum sócio aparece em duas empresas.
MATCH (a:Empresa {cnpj_basico: $cnpj_a}), (b:Empresa {cnpj_basico: $cnpj_b})
WHERE a <> b
MATCH p = shortestPath((a)-[:PARTICIPA_DE*..6]-(b))
RETURN p, length(p) AS quantidade_relacionamentos;

// B. Caminho estrutural mínimo, sem ORIGINADO_DE.
// ATENÇÃO: no recorte este caminho é ESTRUTURAL POR CNAE, não societário. Ele mostra só que as duas
// empresas declaram a mesma atividade econômica; não indica sócio, controle ou relação comercial.
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
// Todos passam por CNAE (coluna cnaes_intermediarios): nenhum passa por Socio.
MATCH (a:Empresa), (b:Empresa)
WHERE a.cnpj_basico < b.cnpj_basico
MATCH p = shortestPath(
  (a)-[:PARTICIPA_DE|POSSUI_ESTABELECIMENTO|EXERCE_CNAE|APLICADA_A|EXTRATO_DE|MENCIONA*..6]-(b)
)
RETURN a.cnpj_basico AS empresa_a,
       b.cnpj_basico AS empresa_b,
       length(p) AS quantidade_relacionamentos,
       [n IN nodes(p) WHERE n:CNAE | n.codigo] AS cnaes_intermediarios,
       size([n IN nodes(p) WHERE n:Socio]) AS socios_no_caminho
ORDER BY quantidade_relacionamentos, empresa_a, empresa_b;

// E. Diagnóstico: por que não há caminho societário no recorte. Só contagens; nenhum nome é exibido.
// E1. Quantas empresas cada nó Socio alcança. Resultado no recorte: 26 sócios, todos com 1 empresa.
// Causa estrutural: socio_id = 'SOC-' + sha256("cnpj_basico:índice:NOME") (scripts/build_canonical_dataset.py).
// Como o cnpj_basico entra no cálculo, a mesma pessoa em duas empresas gera dois socio_id diferentes.
MATCH (s:Socio)
RETURN COUNT { (s)-[:PARTICIPA_DE]->(:Empresa) } AS empresas_por_socio, count(*) AS socios;

// E2. Nomes de sócio presentes em mais de uma empresa. Resultado no recorte: 0.
// Diagnóstico apenas: o projeto NÃO cria vínculo por nome. O zero mostra que nem uma regra de
// identidade por nome encontraria caminho societário neste recorte de 18 empresas.
MATCH (s:Socio)-[:PARTICIPA_DE]->(e:Empresa)
WITH s.nome AS nome, count(DISTINCT e) AS empresas
WHERE empresas > 1
RETURN count(nome) AS nomes_em_mais_de_uma_empresa;

// E3. Sócios pessoa jurídica que são empresas do próprio recorte. Resultado no recorte: 1 sócio PJ, 0 no recorte.
// O QSA não traz o CNPJ do sócio PJ, então mesmo esse caso não liga duas Empresa do grafo.
MATCH (s:Socio)
WHERE s.tipo_pessoa = 'PESSOA JURIDICA'
OPTIONAL MATCH (e:Empresa)
WHERE e.razao_social = s.nome
RETURN count(DISTINCT s) AS socios_pessoa_juridica,
       count(e) AS coincidem_com_empresa_do_recorte;

// F. CNAEs compartilhados: origem de todos os caminhos estruturais do recorte.
// Resultado no recorte: 8 CNAEs em mais de uma empresa (ex.: 4211101 em 00356328 e 01340937).
MATCH (c:CNAE)<-[:EXERCE_CNAE]-(:Estabelecimento)<-[:POSSUI_ESTABELECIMENTO]-(e:Empresa)
WITH c, collect(DISTINCT e.cnpj_basico) AS empresas
WHERE size(empresas) > 1
RETURN c.codigo AS cnae, c.descricao AS descricao, size(empresas) AS quantidade_empresas, empresas
ORDER BY quantidade_empresas DESC, cnae;

// G. CENÁRIO SINTÉTICO — NÃO FAZ PARTE DO RECORTE.
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

// G2. Conferência de limpeza do cenário sintético. Esperado: 0.
MATCH (n:Sintetico) RETURN count(n) AS nos_sinteticos_restantes;
