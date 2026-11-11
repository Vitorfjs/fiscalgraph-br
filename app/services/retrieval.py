"""Recuperação híbrida (vetorial + full-text) e expansão de contexto no grafo Neo4j.

Contrato oficial do dev5 para dev1/dev6: seção 7 de ``docs/recuperacao-hibrida.md``; validador
executável em ``app/services/contract.py``. Depende de ``sentence-transformers``
(``pip install -r requirements.txt -r requirements-dev5.txt``).

Fluxo de ``retrieve_context(question, top_k)``:

1. busca vetorial no índice ``trecho_embedding_vector`` com o embedding da pergunta, gerado pelo
   mesmo ``SentenceEncoder`` (e a mesma segmentação por janelas) usado nos trechos;
2. busca full-text no índice integrado de dev3 ``fiscalgraph_text_fulltext``, restrita ao
   campo ``texto`` e a nós ``Trecho``;
3. fusão das duas listas por Reciprocal Rank Fusion (k=60), sem somar scores brutos;
4. expansão pelo grafo a partir de cada ``Trecho`` selecionado::

       (Trecho)-[:ORIGINADO_DE]->(Fonte)
       (Trecho)-[:EXTRATO_DE]->(Sancao)-[:APLICADA_A]->(Estabelecimento)
               <-[:POSSUI_ESTABELECIMENTO]-(Empresa)<-[:PARTICIPA_DE]-(Socio)
       (Trecho)-[:MENCIONA {status: 'CANDIDATA'}]->(Estabelecimento)

O serviço devolve evidências recuperadas: não gera resposta em linguagem natural nem afirma
responsabilidade jurídica. ``rrf_score`` é relevância de recuperação, não probabilidade de
irregularidade.

``company_paths(cnpj_a, cnpj_b)`` expõe o caminho mínimo entre duas empresas no mesmo formato de
nós e relacionamentos (``app/services/multi_hop.py``).

Uso manual (requer ``.env`` local, Neo4j ativo e embeddings gerados)::

    python -m app.services.retrieval "pergunta" --top-k 5
    python -m app.services.retrieval "pergunta" --formato json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_PIPELINE_VERSION,
    MODEL_NAME,
    VECTOR_INDEX,
    SentenceEncoder,
)
from .ranking import DEFAULT_RRF_K, reciprocal_rank_fusion

try:
    from neo4j.exceptions import ClientError as _Neo4jClientError
except ImportError:  # driver ausente: só ocorre em ambientes mínimos de teste
    class _Neo4jClientError(Exception):  # type: ignore[no-redef]
        pass

ROOT = Path(__file__).resolve().parents[2]

FULLTEXT_INDEX = "fiscalgraph_text_fulltext"  # cypher/01_schema_fiscalgraph.cypher (dev3)
FULLTEXT_FIELD = "texto"
DEFAULT_TOP_K = 5
MAX_TOP_K = 20
# Cada busca devolve mais candidatos do que top_k para que a fusão tenha o que reordenar.
CANDIDATE_MULTIPLIER = 4
MIN_CANDIDATES = 20
MAX_FULLTEXT_TERMS = 16

NO_EVIDENCE_WARNING = "Nenhum trecho foi recuperado; não há evidência suficiente para responder."
MENCIONA_WARNING = (
    "Relações MENCIONA são citações textuais candidatas (status CANDIDATA); "
    "não confirmam vínculo nem responsabilidade."
)

VECTOR_QUERY = """
CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
YIELD node, score
WHERE node:Trecho
RETURN node.trecho_id AS trecho_id, score
ORDER BY score DESC
""".strip()

FULLTEXT_QUERY = """
CALL db.index.fulltext.queryNodes($index_name, $query, {limit: $limit})
YIELD node, score
WHERE node:Trecho
RETURN node.trecho_id AS trecho_id, score
ORDER BY score DESC
LIMIT $limit
""".strip()

# Cada compreensão devolve um prefixo do caminho, para que nós intermediários apareçam
# mesmo quando o salto seguinte não existe. Propriedades volumosas são anuladas na origem.
# O "RegistroCompliance" do contrato corresponde ao rótulo integrado ``Sancao`` (dev3), ligado
# ao CNPJ completo por APLICADA_A -> Estabelecimento (não há REFERE_SE_A no schema integrado).
EXPANSION_QUERY = """
UNWIND $trecho_ids AS tid
MATCH (t:Trecho {trecho_id: tid})
WITH tid, t,
     [p = (t)-[:ORIGINADO_DE]->(:Fonte) | p]
   + [p = (t)-[:EXTRATO_DE]->(:Sancao) | p]
   + [p = (t)-[:EXTRATO_DE]->(:Sancao)-[:APLICADA_A]->(:Estabelecimento) | p]
   + [p = (t)-[:EXTRATO_DE]->(:Sancao)-[:APLICADA_A]->(:Estabelecimento)
          <-[:POSSUI_ESTABELECIMENTO]-(:Empresa) | p]
   + [p = (t)-[:EXTRATO_DE]->(:Sancao)-[:APLICADA_A]->(:Estabelecimento)
          <-[:POSSUI_ESTABELECIMENTO]-(:Empresa)<-[:PARTICIPA_DE]-(:Socio) | p]
   + [p = (t)-[:MENCIONA]->(:Estabelecimento) | p] AS paths
RETURN tid AS trecho_id,
       t.texto AS texto,
       {element_id: elementId(t), labels: labels(t),
        properties: t {.*, embedding: null, texto: null, mencoes_json: null}} AS trecho,
       [p IN paths | {
           nodes: [n IN nodes(p) | {
               element_id: elementId(n), labels: labels(n),
               properties: n {.*, embedding: null, texto: null, mencoes_json: null}}],
           relationships: [rel IN relationships(p) | {
               element_id: elementId(rel), type: type(rel),
               start: elementId(startNode(rel)), end: elementId(endNode(rel)),
               properties: properties(rel)}]
       }] AS paths
""".strip()

EMBEDDING_STATUS_QUERY = """
MATCH (t:Trecho)
WHERE t.embedding IS NOT NULL
RETURN count(t) AS com_embedding,
       count(CASE WHEN t.embedding_model = $model AND t.embedding_pipeline_version = $version
                  THEN 1 END) AS na_versao_atual
""".strip()

CYPHER_SUMMARY = (
    "// 1. Busca vetorial (índice " + VECTOR_INDEX + ")\n" + VECTOR_QUERY + ";\n\n"
    "// 2. Busca full-text (índice " + FULLTEXT_INDEX + ", campo " + FULLTEXT_FIELD + ")\n"
    + FULLTEXT_QUERY + ";\n\n"
    "// 3. Fusão por Reciprocal Rank Fusion em Python (app/services/ranking.py).\n\n"
    "// 4. Expansão pelo grafo dos trechos selecionados\n" + EXPANSION_QUERY + ";"
)

# Rótulo → propriedade que identifica o nó de forma estável. A ordem define o rótulo principal.
NODE_KEYS: Tuple[Tuple[str, str], ...] = (
    ("Trecho", "trecho_id"),
    ("Sancao", "registro_id"),
    ("Fonte", "fonte_id"),
    ("Empresa", "cnpj_basico"),
    ("Estabelecimento", "cnpj"),
    ("Socio", "socio_id"),
    ("CNAE", "codigo"),
)

_COMPLIANCE_PROPERTIES = (
    "registro_id", "tipo_registro", "orgao_responsavel", "numero_processo", "data_inicio",
    "data_fim", "situacao", "descricao", "cnpj_sancionado", "url_fonte", "fonte_id", "registro_origem",
)
# Propriedades mínimas para evidência. ``embedding`` e textos longos nunca são devolvidos aqui
# (o texto do trecho já está em ``chunks``).
EVIDENCE_PROPERTIES: Dict[str, Tuple[str, ...]] = {
    "Trecho": ("trecho_id", "registro_id", "fonte_id", "url_fonte", "registro_origem",
               "metodo_extracao", "embedding_model", "embedding_pipeline_version", "embedding_windows"),
    "Sancao": _COMPLIANCE_PROPERTIES,
    "Fonte": ("fonte_id", "nome", "orgao_responsavel", "url", "data_coleta", "competencia",
              "arquivo_origem"),
    "Empresa": ("cnpj_basico", "razao_social", "natureza_juridica", "porte"),
    "Estabelecimento": ("cnpj", "cnpj_basico", "nome_fantasia", "situacao_cadastral", "uf", "municipio"),
    "Socio": ("socio_id", "tipo_pessoa", "qualificacao", "data_entrada"),
    "CNAE": ("codigo", "descricao"),
}
_ALWAYS_EXCLUDED = frozenset({"embedding", "texto", "mencoes_json"})

# Palavras funcionais e de pergunta removidas da busca full-text. O analisador do índice
# (standard-no-stop-words) não remove stopwords, e com OR elas trariam quase todos os trechos.
STOPWORDS_PT = frozenset("""
a o as os um uma uns umas de da do das dos e em no na nos nas ao aos à às por pelo pela pelos
pelas para pra com sem sob sobre entre até que qual quais quem como onde quando se é são foi
foram ser há ou mais menos muito muita seu sua seus suas este esta estes estas esse essa esses
essas isso isto aquele aquela me meu minha não nao sim já tem têm possui possuem existe existem
algum alguma alguns algumas lista liste listar mostre mostrar
""".split())

_NUMBER_WITH_SEPARATORS = re.compile(r"\d+(?:[.\-/]\d+)+")
_SEPARATORS = re.compile(r"[.\-/]")
_TOKEN = re.compile(r"\w+")


def build_fulltext_query(question: str, field: str = FULLTEXT_FIELD, max_terms: int = MAX_FULLTEXT_TERMS) -> str:
    """Converte a pergunta em consulta Lucene segura: ``texto:(termo1 OR termo2 ...)``.

    - número com separador gera duas formas: a contínua (``8666``, CNPJ com 14 dígitos) e uma
      frase com a pontuação original (``"12.846"``, ``"01.340.937/0001-79"``), porque o
      analisador do índice mantém ``01.340.937`` como um token e quebra em ``/`` e ``-``;
    - as demais palavras contêm só letras, dígitos e ``_``, e as frases só dígitos e ``.-/``:
      nenhum operador Lucene digitado pelo usuário chega ao índice;
    - termos em minúsculas, então ``and``/``or``/``not`` digitados não viram operadores;
    - OR em vez de AND: exigir todos os termos de uma pergunta em linguagem natural quase
      sempre zera o resultado; a relevância Lucene e o RRF cuidam da ordenação.
    """
    text = question.lower()
    terms: List[str] = []

    def add(term: str) -> None:
        if term not in terms and len(terms) < max_terms:
            terms.append(term)

    for match in _NUMBER_WITH_SEPARATORS.finditer(text):
        add(_SEPARATORS.sub("", match.group()))
        add(f'"{match.group()}"')
    for token in _TOKEN.findall(_NUMBER_WITH_SEPARATORS.sub(" ", text)):
        if len(token) >= 2 and token not in STOPWORDS_PT:
            add(token)
    if not terms:
        return ""
    return f"{field}:(" + " OR ".join(terms) + ")"


def _validate_question(question: Any) -> str:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("A pergunta não pode ser vazia.")
    return question.strip()


def _normalize_top_k(top_k: Any, warnings: List[str]) -> int:
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise ValueError("top_k precisa ser um inteiro.")
    if top_k < 1:
        raise ValueError("top_k precisa ser maior ou igual a 1.")
    if top_k > MAX_TOP_K:
        warnings.append(f"top_k={top_k} reduzido para o máximo de {MAX_TOP_K}.")
        return MAX_TOP_K
    return top_k


def _error_message(exc: Exception) -> str:
    return getattr(exc, "message", None) or str(exc)


def _primary_label(labels: Iterable[str]) -> Tuple[str, Optional[str]]:
    labels = list(labels)
    for label, key in NODE_KEYS:
        if label in labels:
            return label, key
    return (labels[0] if labels else "Node"), None


def node_payload(node: Dict[str, Any]) -> Dict[str, Any]:
    """Nó do contrato: ``{"id": "Rotulo:chave", "label": ..., "properties": {...mínimas}}``."""
    label, key = _primary_label(node.get("labels") or [])
    raw = node.get("properties") or {}
    value = raw.get(key) if key else None
    node_id = f"{label}:{value}" if value not in (None, "") else f"{label}:{node['element_id']}"
    allowed = EVIDENCE_PROPERTIES.get(label)
    properties = {
        name: item for name, item in raw.items()
        if item is not None and name not in _ALWAYS_EXCLUDED and (allowed is None or name in allowed)
    }
    # Minimização: nome de sócio só é devolvido quando o sócio é pessoa jurídica.
    if label == "Socio" and raw.get("tipo_pessoa") == "PESSOA JURIDICA" and raw.get("nome"):
        properties["nome"] = raw["nome"]
    return {"id": node_id, "label": label, "properties": properties}


def _maximal_paths(paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove caminhos vazios, repetidos ou que são prefixo de outro caminho do mesmo trecho."""
    signatures = [tuple(rel["element_id"] for rel in path["relationships"]) for path in paths]
    kept, seen = [], set()
    for path, signature in zip(paths, signatures):
        if not signature or signature in seen:
            continue
        is_prefix = any(
            len(other) > len(signature) and other[: len(signature)] == signature for other in signatures
        )
        if not is_prefix:
            kept.append(path)
            seen.add(signature)
    return kept


def path_to_text(path: Dict[str, Any], ids: Dict[str, str]) -> str:
    """Notação Cypher legível, respeitando a direção de cada relacionamento."""
    nodes, relationships = path["nodes"], path["relationships"]
    parts = [f"({ids[nodes[0]['element_id']]})"]
    for index, rel in enumerate(relationships):
        previous = nodes[index]["element_id"]
        arrow = f"-[:{rel['type']}]->" if rel["start"] == previous else f"<-[:{rel['type']}]-"
        parts.append(arrow + f"({ids[nodes[index + 1]['element_id']]})")
    return "".join(parts)


def _blank_to_none(value: Any) -> Optional[str]:
    return None if value in (None, "") else value


def _first_property(paths: List[Dict[str, Any]], label: str, prop: str) -> Optional[str]:
    for path in paths:
        for node in path["nodes"]:
            if label in (node.get("labels") or []):
                value = _blank_to_none((node.get("properties") or {}).get(prop))
                if value is not None:
                    return value
    return None


def _dedupe(items: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(items))


def cnpj_identifiers(text: str) -> List[str]:
    """CNPJs de 14 posições (formatados ou contínuos, numéricos ou alfanuméricos) citados no texto.

    Usa ``extract_mentions`` do dev4 (só a regra estrutural de CNPJ, sem spaCy), o mesmo critério
    que gera ``MENCIONA``. Valores normalizados, sem pontuação.
    """
    from pipeline.text_to_graph.extractor import extract_mentions  # import tardio: só quando usado

    return list(dict.fromkeys(m["valor"] for m in extract_mentions(text or "") if m.get("tipo") == "CNPJ"))


def _identifier_matches(query_identifiers: List[str], texto: str) -> List[str]:
    if not query_identifiers:
        return []
    found = set(cnpj_identifiers(texto))
    return [identifier for identifier in query_identifiers if identifier in found]


def identifier_warning(query_identifiers: List[str], chunks: List[Dict[str, Any]]) -> Optional[str]:
    """A busca semântica não distingue números: avisa quando o 1º trecho não contém o CNPJ da pergunta.

    Não reordena os resultados (a ordem continua sendo a do RRF); só aponta a correspondência literal.
    """
    if not query_identifiers or not chunks:
        return None
    missing = [i for i in query_identifiers if i not in chunks[0]["identifier_matches"]]
    if not missing:
        return None
    parts = []
    for identifier in missing:
        position, chunk = next(((p, c) for p, c in enumerate(chunks, 1) if identifier in c["identifier_matches"]),
                               (None, None))
        if chunk is None:
            parts.append(f"nenhum trecho recuperado contém o CNPJ {identifier}")
        else:
            parts.append(f"o CNPJ {identifier} aparece literalmente no {position}º trecho "
                         f"({chunk['trecho_id']}, registro {chunk['registro_id']})")
    return ("A pergunta cita CNPJ e o 1º trecho não o contém literalmente: " + "; ".join(parts)
            + ". A busca semântica não distingue números de CNPJ; confira identifier_matches.")


def build_response(
    question: str,
    fused: List[Dict[str, Any]],
    scores: Dict[str, Dict[str, float]],
    expansion: Dict[str, Dict[str, Any]],
    warnings: List[str],
    parameters: Dict[str, Any],
    query_identifiers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Monta a resposta do contrato a partir do ranking fundido e da expansão pelo grafo."""
    chunks: List[Dict[str, Any]] = []
    nodes: Dict[str, Dict[str, Any]] = {}
    relationships: Dict[str, Dict[str, Any]] = {}

    for item in fused:
        trecho_id = item["trecho_id"]
        row = expansion.get(trecho_id)
        if row is None:
            warnings.append(f"Trecho {trecho_id} saiu do grafo entre a busca e a expansão; descartado.")
            continue
        paths = row.get("paths") or []
        ids: Dict[str, str] = {}
        for node in [row["trecho"]] + [n for path in paths for n in path["nodes"]]:
            payload = node_payload(node)
            ids[node["element_id"]] = payload["id"]
            nodes.setdefault(payload["id"], payload)
        for path in paths:
            for rel in path["relationships"]:
                relationships.setdefault(rel["element_id"], {
                    "source": ids[rel["start"]],
                    "target": ids[rel["end"]],
                    "type": rel["type"],
                    "properties": dict(rel.get("properties") or {}),
                })

        trecho = row["trecho"].get("properties") or {}
        compliance_id = _first_property(paths, "Sancao", "registro_id")
        chunks.append({
            "trecho_id": trecho_id,
            "texto": row.get("texto") or "",
            "registro_id": _blank_to_none(trecho.get("registro_id")) or compliance_id,
            "fonte_id": _blank_to_none(trecho.get("fonte_id")) or _first_property(paths, "Fonte", "fonte_id"),
            "url_fonte": _blank_to_none(trecho.get("url_fonte")) or _first_property(paths, "Fonte", "url"),
            "vector_rank": item["vector_rank"],
            "fulltext_rank": item["fulltext_rank"],
            "rrf_score": item["rrf_score"],
            # Campos adicionais (o contrato define o mínimo). Scores brutos são só informativos:
            # estão em escalas diferentes e não entram na fusão.
            "vector_score": scores["vector"].get(trecho_id),
            "fulltext_score": scores["fulltext"].get(trecho_id),
            "graph_paths": [path_to_text(path, ids) for path in _maximal_paths(paths)],
            # CNPJs da pergunta que aparecem literalmente no texto deste trecho (regra do dev4).
            "identifier_matches": _identifier_matches(query_identifiers or [], row.get("texto") or ""),
        })

    warning = identifier_warning(query_identifiers or [], chunks)
    if warning:
        warnings.append(warning)
    if any(rel["type"] == "MENCIONA" for rel in relationships.values()):
        warnings.append(MENCIONA_WARNING)
    if not chunks:
        warnings.append(NO_EVIDENCE_WARNING)

    return {
        "query": question,
        "retrieval_mode": "hybrid",
        "chunks": chunks,
        "nodes": list(nodes.values()),
        "relationships": list(relationships.values()),
        "cypher": CYPHER_SUMMARY,
        "warnings": _dedupe(warnings),
        "parameters": parameters,
    }


class GraphHybridRetriever:
    """Recuperador híbrido sobre o Neo4j. Reutilize a instância: o modelo é carregado uma vez."""

    def __init__(self, driver: Any, encoder: Any = None, *, database: Optional[str] = None,
                 rrf_k: int = DEFAULT_RRF_K):
        reciprocal_rank_fusion([], [], k=rrf_k)  # valida k cedo
        self.driver = driver
        self.database = database
        self.rrf_k = rrf_k
        self._encoder = encoder
        self._owns_driver = False
        self._embedding_status: Optional[Dict[str, int]] = None  # conferido uma vez por instância

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None, encoder: Any = None) -> "GraphHybridRetriever":
        """Cria o driver a partir de ``.env`` (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE)."""
        from dotenv import load_dotenv
        from neo4j import GraphDatabase

        load_dotenv(env_file or ROOT / ".env")
        password = os.getenv("NEO4J_PASSWORD")
        if not password or password == "change_this_password_before_starting":
            raise RuntimeError("Configure NEO4J_PASSWORD no .env local antes de usar o serviço.")
        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), password),
        )
        retriever = cls(driver, encoder, database=os.getenv("NEO4J_DATABASE") or None)
        retriever._owns_driver = True
        return retriever

    def close(self) -> None:
        if self._owns_driver:
            self.driver.close()

    @property
    def encoder(self) -> Any:
        if self._encoder is None:
            self._encoder = SentenceEncoder()
        return self._encoder

    def _search(self, session: Any, cypher: str, warnings: List[str], failure: str,
                **params: Any) -> Optional[List[Dict[str, Any]]]:
        """Executa uma das buscas. Devolve ``None`` (e registra aviso) se o índice falhar."""
        try:
            return [{"trecho_id": record["trecho_id"], "score": record["score"]}
                    for record in session.run(cypher, params)
                    if record["trecho_id"] is not None]
        except _Neo4jClientError as exc:
            warnings.append(f"{failure}: {_error_message(exc)}")
            return None

    @property
    def pipeline_version(self) -> str:
        return getattr(self.encoder, "pipeline_version", EMBEDDING_PIPELINE_VERSION)

    def _embedding_version_warning(self, session: Any) -> Optional[str]:
        """Avisa se os vetores gravados vêm de outra estratégia que a usada na pergunta.

        Conferido uma vez por instância; após regenerar os embeddings, crie um novo recuperador.
        """
        if self._embedding_status is None:
            try:
                record = next(iter(session.run(EMBEDDING_STATUS_QUERY, {
                    "model": MODEL_NAME, "version": self.pipeline_version})), None)
            except _Neo4jClientError:
                return None
            self._embedding_status = {
                "com_embedding": record["com_embedding"] if record else 0,
                "na_versao_atual": record["na_versao_atual"] if record else 0,
            }
        status = self._embedding_status
        outdated = status["com_embedding"] - status["na_versao_atual"]
        if outdated > 0:
            return (f"{outdated} de {status['com_embedding']} Trecho têm embedding de outro modelo ou de outra "
                    f"versão da estratégia (atual: {self.pipeline_version}); execute "
                    "python scripts/generate_embeddings.py.")
        return None

    def retrieve_context(self, question: str, top_k: int = DEFAULT_TOP_K) -> Dict[str, Any]:
        question = _validate_question(question)
        warnings: List[str] = []
        top_k = _normalize_top_k(top_k, warnings)
        candidate_k = max(top_k * CANDIDATE_MULTIPLIER, MIN_CANDIDATES)
        fulltext_query = build_fulltext_query(question)
        query_identifiers = cnpj_identifiers(question)
        embedding = self.encoder.encode([question])[0]

        with self.driver.session(database=self.database) as session:
            version_warning = self._embedding_version_warning(session)
            if version_warning:
                warnings.append(version_warning)
            vector_result = self._search(
                session, VECTOR_QUERY, warnings,
                f"Busca vetorial indisponível no índice {VECTOR_INDEX}; resultado apenas full-text",
                index_name=VECTOR_INDEX, limit=candidate_k, embedding=embedding,
            )
            vector_rows = vector_result or []
            fulltext_result: Optional[List[Dict[str, Any]]] = None
            if fulltext_query:
                fulltext_result = self._search(
                    session, FULLTEXT_QUERY, warnings,
                    f"Busca full-text indisponível no índice {FULLTEXT_INDEX}; resultado apenas vetorial",
                    index_name=FULLTEXT_INDEX, query=fulltext_query, limit=candidate_k,
                )
            else:
                warnings.append("A pergunta não gerou termos para a busca full-text; resultado apenas vetorial.")
            fulltext_rows = fulltext_result or []

            if vector_result == []:
                warnings.append(
                    "Busca vetorial sem resultados: nenhum Trecho possui embedding. "
                    "Execute scripts/generate_embeddings.py."
                )
            if vector_rows and fulltext_result == []:
                warnings.append(
                    "Nenhum termo da pergunta aparece nos trechos indexados; os resultados vêm só da "
                    "similaridade semântica e podem ter baixa relevância."
                )

            fused = reciprocal_rank_fusion(
                [row["trecho_id"] for row in vector_rows],
                [row["trecho_id"] for row in fulltext_rows],
                k=self.rrf_k,
            )[:top_k]
            expansion = {}
            if fused:
                result = session.run(EXPANSION_QUERY, trecho_ids=[item["trecho_id"] for item in fused])
                expansion = {record["trecho_id"]: {
                    "texto": record["texto"], "trecho": record["trecho"], "paths": record["paths"],
                } for record in result}

        scores = {
            "vector": {row["trecho_id"]: row["score"] for row in vector_rows},
            "fulltext": {row["trecho_id"]: row["score"] for row in fulltext_rows},
        }
        # retrieval_mode continua "hybrid" (contrato); estes campos dizem o que de fato contribuiu.
        search_status = {
            "vector": search_state(vector_result),
            "fulltext": search_state(fulltext_result, executed=bool(fulltext_query)),
        }
        parameters = {
            "top_k": top_k,
            "candidate_k": candidate_k,
            "rrf_k": self.rrf_k,
            # Máximo teórico: trecho em 1º lugar nas duas buscas. Útil para o dev1 normalizar
            # retrieval_relevance (rrf_score / rrf_max_score); não é probabilidade.
            "rrf_max_score": 2.0 / (self.rrf_k + 1),
            "active_searches": [name for name, state in search_status.items() if state == "com_resultados"],
            "search_status": search_status,
            "embedding_model": MODEL_NAME,
            "embedding_dimensions": EMBEDDING_DIMENSIONS,
            "embedding_pipeline_version": self.pipeline_version,
            "vector_index": VECTOR_INDEX,
            "fulltext_index": FULLTEXT_INDEX,
            "fulltext_query": fulltext_query or None,
            "query_identifiers": query_identifiers,
        }
        return build_response(question, fused, scores, expansion, warnings, parameters, query_identifiers)

    def company_paths(self, cnpj_a: str, cnpj_b: str, max_hops: int = 6) -> Dict[str, Any]:
        """Caminhos mínimos societário e estrutural entre duas empresas (``app/services/multi_hop.py``).

        Não usa o modelo de embeddings.
        """
        from .multi_hop import find_company_paths  # import local: multi_hop importa este módulo

        with self.driver.session(database=self.database) as session:
            return find_company_paths(session, cnpj_a, cnpj_b, max_hops)


def search_state(result: Optional[List[Dict[str, Any]]], executed: bool = True) -> str:
    """``com_resultados`` | ``sem_resultados`` | ``indisponivel`` (índice falhou) | ``nao_executada``."""
    if not executed:
        return "nao_executada"
    if result is None:
        return "indisponivel"
    return "com_resultados" if result else "sem_resultados"


_default_retriever: Optional[GraphHybridRetriever] = None


def _shared_retriever() -> GraphHybridRetriever:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = GraphHybridRetriever.from_env()
    return _default_retriever


def retrieve_context(question: str, top_k: int = DEFAULT_TOP_K) -> Dict[str, Any]:
    """Ponto de entrada do contrato. Usa um recuperador compartilhado configurado pelo ``.env``."""
    return _shared_retriever().retrieve_context(question, top_k)


def company_paths(cnpj_a: str, cnpj_b: str, max_hops: int = 6) -> Dict[str, Any]:
    """Caminho mínimo entre duas empresas, com o recuperador compartilhado (não carrega o modelo)."""
    return _shared_retriever().company_paths(cnpj_a, cnpj_b, max_hops)


def format_text(result: Dict[str, Any]) -> str:
    lines = [f"Pergunta: {result['query']}",
             f"Modo: {result['retrieval_mode']} | parâmetros: {json.dumps(result['parameters'], ensure_ascii=False)}"]
    for position, chunk in enumerate(result["chunks"], start=1):
        texto = " ".join(chunk["texto"].split())
        lines += [
            "",
            f"#{position} trecho_id={chunk['trecho_id']} rrf_score={chunk['rrf_score']:.6f} "
            f"vector_rank={chunk['vector_rank']} fulltext_rank={chunk['fulltext_rank']}",
            f"   registro_id={chunk['registro_id']} fonte_id={chunk['fonte_id']} url_fonte={chunk['url_fonte']}",
            f"   texto: {texto[:220]}{'…' if len(texto) > 220 else ''}",
        ]
        if result["parameters"].get("query_identifiers"):
            lines.append(f"   identifier_matches={chunk['identifier_matches']}")
        lines += [f"   caminho: {path}" for path in chunk["graph_paths"]]
    lines += ["", f"Nós: {len(result['nodes'])} | relacionamentos: {len(result['relationships'])}"]
    lines += [f"Aviso: {warning}" for warning in result["warnings"]]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Consulta manual da recuperação híbrida (dev5).")
    parser.add_argument("question", help="Pergunta em linguagem natural")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--formato", choices=("texto", "json"), default="texto")
    args = parser.parse_args(argv)
    retriever = GraphHybridRetriever.from_env()
    try:
        result = retriever.retrieve_context(args.question, args.top_k)
    finally:
        retriever.close()
    if args.formato == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
