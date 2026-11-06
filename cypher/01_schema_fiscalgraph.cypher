// FiscalGraph BR — schema LPG para Neo4j 5 Community.
// Execute cada comando no Neo4j Browser. Todos os identificadores são strings.

// 1. Constraints de unicidade dos nós estruturados.
CREATE CONSTRAINT empresa_cnpj_basico_unique IF NOT EXISTS
FOR (n:Empresa) REQUIRE n.cnpj_basico IS UNIQUE;

CREATE CONSTRAINT estabelecimento_cnpj_unique IF NOT EXISTS
FOR (n:Estabelecimento) REQUIRE n.cnpj IS UNIQUE;

CREATE CONSTRAINT socio_socio_id_unique IF NOT EXISTS
FOR (n:Socio) REQUIRE n.socio_id IS UNIQUE;

CREATE CONSTRAINT cnae_codigo_unique IF NOT EXISTS
FOR (n:CNAE) REQUIRE n.codigo IS UNIQUE;

CREATE CONSTRAINT sancao_registro_id_unique IF NOT EXISTS
FOR (n:Sancao) REQUIRE n.registro_id IS UNIQUE;

CREATE CONSTRAINT fonte_fonte_id_unique IF NOT EXISTS
FOR (n:Fonte) REQUIRE n.fonte_id IS UNIQUE;

// 2. Constraint necessária ao carregador Text-to-Graph (Dev4).
CREATE CONSTRAINT trecho_trecho_id_unique IF NOT EXISTS
FOR (n:Trecho) REQUIRE n.trecho_id IS UNIQUE;

// 3. Índices de busca por campos usados em filtros e consultas planejadas.
// As constraints de unicidade acima já criam seus próprios índices de apoio.
CREATE INDEX estabelecimento_situacao_cadastral_idx IF NOT EXISTS
FOR (n:Estabelecimento) ON (n.situacao_cadastral);

CREATE INDEX estabelecimento_localizacao_idx IF NOT EXISTS
FOR (n:Estabelecimento) ON (n.uf, n.municipio);

CREATE INDEX empresa_porte_idx IF NOT EXISTS
FOR (n:Empresa) ON (n.porte);

CREATE INDEX sancao_tipo_registro_idx IF NOT EXISTS
FOR (n:Sancao) ON (n.tipo_registro);

CREATE INDEX sancao_numero_processo_idx IF NOT EXISTS
FOR (n:Sancao) ON (n.numero_processo);

// 4. Índice full-text inicial. Inclui Trecho.texto para uso pelo Dev5.
// A busca full-text é invocada explicitamente por procedimento; não é automática.
CREATE FULLTEXT INDEX fiscalgraph_text_fulltext IF NOT EXISTS
FOR (n:Empresa|Socio|Sancao|Trecho)
ON EACH [n.razao_social, n.nome, n.descricao, n.observacoes, n.fundamentacao_legal, n.texto];

// 5. Após a execução, confira os estados dos índices com:
// SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state
// RETURN name, type, entityType, labelsOrTypes, properties, state ORDER BY name;
