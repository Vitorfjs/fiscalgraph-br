// FiscalGraph BR — consultas de validação do schema e da carga canônica.
// Execute uma consulta por vez no Neo4j Browser.

// A. Constraints existentes. Esperadas: 7 constraints de unicidade.
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;

// B. Índices existentes e seus estados. Esperar state = ONLINE.
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state, populationPercent
RETURN name, type, entityType, labelsOrTypes, properties, state, populationPercent
ORDER BY name;

// C. Contagem dos nós estruturados depois da carga canônica.
MATCH (n:Empresa) RETURN 'Empresa' AS label, count(n) AS quantidade
UNION ALL
MATCH (n:Estabelecimento) RETURN 'Estabelecimento' AS label, count(n) AS quantidade
UNION ALL
MATCH (n:Socio) RETURN 'Socio' AS label, count(n) AS quantidade
UNION ALL
MATCH (n:CNAE) RETURN 'CNAE' AS label, count(n) AS quantidade
UNION ALL
MATCH (n:Sancao) RETURN 'Sancao' AS label, count(n) AS quantidade
UNION ALL
MATCH (n:Fonte) RETURN 'Fonte' AS label, count(n) AS quantidade
UNION ALL
MATCH (n:Trecho) RETURN 'Trecho' AS label, count(n) AS quantidade
ORDER BY label;

// D. Contagem dos relacionamentos estruturados.
MATCH (:Socio)-[r:PARTICIPA_DE]->(:Empresa)
RETURN 'PARTICIPA_DE' AS relacionamento, count(r) AS quantidade
UNION ALL
MATCH (:Empresa)-[r:POSSUI_ESTABELECIMENTO]->(:Estabelecimento)
RETURN 'POSSUI_ESTABELECIMENTO' AS relacionamento, count(r) AS quantidade
UNION ALL
MATCH (:Estabelecimento)-[r:EXERCE_CNAE]->(:CNAE)
RETURN 'EXERCE_CNAE' AS relacionamento, count(r) AS quantidade
UNION ALL
MATCH (:Sancao)-[r:APLICADA_A]->(:Estabelecimento)
RETURN 'APLICADA_A' AS relacionamento, count(r) AS quantidade
UNION ALL
MATCH (n)-[r:ORIGINADO_DE]->(:Fonte)
RETURN 'ORIGINADO_DE' AS relacionamento, count(r) AS quantidade
UNION ALL
MATCH (:Trecho)-[r:EXTRATO_DE]->(:Sancao)
RETURN 'EXTRATO_DE' AS relacionamento, count(r) AS quantidade
UNION ALL
MATCH (:Trecho)-[r:MENCIONA]->(:Estabelecimento)
RETURN 'MENCIONA' AS relacionamento, count(r) AS quantidade
ORDER BY relacionamento;

// E. Integridade: estabelecimentos sem Empresa correspondente. Esperado: 0.
MATCH (e:Estabelecimento)
OPTIONAL MATCH (emp:Empresa {cnpj_basico: e.cnpj_basico})
WITH e, emp WHERE emp IS NULL
RETURN count(e) AS estabelecimentos_sem_empresa;

// F. Integridade: sócios sem vínculo PARTICIPA_DE com Empresa. Esperado: 0.
MATCH (s:Socio)
WHERE NOT EXISTS { MATCH (s)-[:PARTICIPA_DE]->(:Empresa) }
RETURN count(s) AS socios_sem_empresa;

// G. Integridade: sanções sem Estabelecimento de CNPJ exato. Esperado: 0.
MATCH (s:Sancao)
OPTIONAL MATCH (e:Estabelecimento {cnpj: s.cnpj_sancionado})
WITH s, e WHERE e IS NULL
RETURN count(s) AS sancoes_sem_estabelecimento;

// H. Integridade: CNAEs sem nós CNAE. Esperado: 0.
MATCH (e:Estabelecimento)-[r:EXERCE_CNAE]->(c)
WHERE NOT (c:CNAE)
RETURN count(r) AS relacionamentos_cnae_com_destino_invalido;

// I. Integridade: entidades sem procedência. Esperado: 0 para os nós estruturados.
MATCH (n)
WHERE (n:Empresa OR n:Estabelecimento OR n:Socio OR n:CNAE OR n:Sancao OR n:Trecho)
  AND NOT EXISTS { MATCH (n)-[:ORIGINADO_DE]->(:Fonte) }
RETURN labels(n) AS labels, count(n) AS entidades_sem_fonte
ORDER BY labels;

// J. Verificação do Text-to-Graph após a carga do Dev4.
MATCH (t:Trecho)
OPTIONAL MATCH (t)-[r:EXTRATO_DE]->(:Sancao)
WITH t, count(r) AS total_registros_vinculados
WHERE total_registros_vinculados = 0
RETURN count(t) AS trechos_sem_registro_de_compliance;

MATCH (t:Trecho)
OPTIONAL MATCH (t)-[r:ORIGINADO_DE]->(:Fonte)
WITH t, count(r) AS total_fontes
WHERE total_fontes = 0
RETURN count(t) AS trechos_sem_fonte;
