// FiscalGraph BR — índice vetorial de Trecho (dev5).
// O schema de dev3 (01_schema_fiscalgraph.cypher) não cria índice vetorial; docs/validacao-neo4j.md
// atribui o índice e os embeddings ao dev5. scripts/generate_embeddings.py executa este mesmo
// comando (IF NOT EXISTS) e confere a configuração antes de gravar embeddings.
//
// Modelo: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 → 384 dimensões.
// Similaridade: cosine (os vetores são gravados normalizados).
// Alterar dimensão ou modelo exige ajuste coordenado com dev3 e reprocessamento de todos os Trecho.

CREATE VECTOR INDEX trecho_embedding_vector IF NOT EXISTS
FOR (t:Trecho) ON (t.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 384,
  `vector.similarity_function`: 'cosine'
}};

// Conferência: esperar type = VECTOR, state = ONLINE, 384 dimensões e similaridade COSINE.
SHOW INDEXES
YIELD name, type, labelsOrTypes, properties, options, state
WHERE name = 'trecho_embedding_vector'
RETURN name, type, labelsOrTypes, properties, state,
       options.indexConfig['vector.dimensions'] AS dimensoes,
       options.indexConfig['vector.similarity_function'] AS similaridade;

// Cobertura dos embeddings (depois de python scripts/generate_embeddings.py).
MATCH (t:Trecho)
RETURN count(t) AS trechos,
       count(t.embedding) AS com_embedding,
       min(size(t.embedding)) AS dimensao_min,
       max(size(t.embedding)) AS dimensao_max,
       collect(DISTINCT t.embedding_model) AS modelos;
