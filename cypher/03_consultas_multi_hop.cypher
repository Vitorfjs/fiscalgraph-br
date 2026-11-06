// Consultas de exemplo do FiscalGraph BR.
// No Neo4j Browser, defina o parâmetro antes das consultas, por exemplo:
// :param cnpj_basico => '00002776';

// 1. Perfil empresarial e estabelecimentos.
MATCH (emp:Empresa {cnpj_basico: $cnpj_basico})
OPTIONAL MATCH (emp)-[:POSSUI_ESTABELECIMENTO]->(est:Estabelecimento)
RETURN emp.cnpj_basico AS cnpj_basico,
       emp.razao_social AS razao_social,
       collect(DISTINCT {
           cnpj: est.cnpj,
           situacao: est.situacao_cadastral,
           uf: est.uf,
           municipio: est.municipio
       }) AS estabelecimentos;

// 1b. CNAEs por estabelecimento.
MATCH (emp:Empresa {cnpj_basico: $cnpj_basico})-[:POSSUI_ESTABELECIMENTO]->(est:Estabelecimento)
OPTIONAL MATCH (est)-[rel:EXERCE_CNAE]->(c:CNAE)
RETURN est.cnpj AS estabelecimento,
       collect(DISTINCT {codigo: c.codigo, descricao: c.descricao, principal: rel.principal}) AS cnaes;

// 2. Registros CEIS/CNEP associados a estabelecimentos da empresa.
MATCH (emp:Empresa {cnpj_basico: $cnpj_basico})
      -[:POSSUI_ESTABELECIMENTO]->(est:Estabelecimento)
      <-[:APLICADA_A]-(s:Sancao)
RETURN emp.razao_social AS empresa,
       est.cnpj AS estabelecimento,
       s.registro_id AS registro_id,
       s.tipo_registro AS cadastro,
       s.descricao AS descricao,
       s.data_inicio AS data_inicio,
       s.data_fim AS data_fim,
       s.numero_processo AS processo
ORDER BY s.data_inicio;

// 3. Evidências textuais correspondentes aos registros de compliance.
// O resultado mostra o trecho e a fonte, sem tratar menção como prova.
MATCH (emp:Empresa {cnpj_basico: $cnpj_basico})
      -[:POSSUI_ESTABELECIMENTO]->(est:Estabelecimento)
      <-[:APLICADA_A]-(s:Sancao)
      <-[:EXTRATO_DE]-(t:Trecho)
MATCH (t)-[:ORIGINADO_DE]->(f:Fonte)
RETURN emp.razao_social AS empresa,
       s.registro_id AS registro_id,
       t.trecho_id AS trecho_id,
       t.texto AS evidencia_textual,
       f.nome AS fonte,
       f.url AS url_fonte,
       t.registro_origem AS registro_origem
ORDER BY s.registro_id;

// 4. Sócios registrados para uma empresa específica.
// socio_id é uma ocorrência vinculada à empresa; não usar nome para deduplicar pessoas.
MATCH (s:Socio)-[r:PARTICIPA_DE]->(emp:Empresa {cnpj_basico: $cnpj_basico})
RETURN emp.razao_social AS empresa,
       s.socio_id AS socio_id,
       s.nome AS nome_publicado,
       s.tipo_pessoa AS tipo_pessoa,
       r.qualificacao AS qualificacao,
       r.data_entrada AS data_entrada
ORDER BY s.nome;
