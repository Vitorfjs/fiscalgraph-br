// FiscalGraph BR — índice vetorial de Trecho (dev5).
// O schema de dev3 (01_schema_fiscalgraph.cypher) não cria índice vetorial; docs/validacao-neo4j.md
// atribui o índice e os embeddings ao dev5. scripts/generate_embeddings.py executa este mesmo
// comando (IF NOT EXISTS) e confere a configuração antes de gravar embeddings.
//
// Modelo: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 → 384 dimensões.
// Similaridade: cosine (os vetores são gravados normalizados).
// Cada Trecho tem um único vetor, calculado sobre o texto inteiro por janelas de tokens
// (app/services/embeddings.py); o índice não muda com a estratégia de segmentação.
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
// Esperado: todos os Trecho com embedding de 384 dimensões, norma 1 (cosine), a mesma versão de
// estratégia (embedding_pipeline_version) e pelo menos 1 janela por trecho.
MATCH (t:Trecho)
WITH t, CASE WHEN t.embedding IS NULL THEN null
             ELSE sqrt(reduce(s = 0.0, x IN t.embedding | s + x * x)) END AS norma
RETURN count(t) AS trechos,
       count(t.embedding) AS com_embedding,
       min(size(t.embedding)) AS dimensao_min,
       max(size(t.embedding)) AS dimensao_max,
       round(min(norma) * 1000000) / 1000000 AS norma_min,
       round(max(norma) * 1000000) / 1000000 AS norma_max,
       collect(DISTINCT t.embedding_model) AS modelos,
       collect(DISTINCT t.embedding_pipeline_version) AS versoes,
       sum(t.embedding_windows) AS janelas,
       max(t.embedding_windows) AS janelas_max;
