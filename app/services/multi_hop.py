"""Caminho mínimo entre duas empresas (``shortestPath``) no formato de nós e relacionamentos do dev5.

Complementa ``retrieve_context``. Lá, o subgrafo parte dos trechos recuperados
(Trecho → Sancao → Estabelecimento ← Empresa ← Socio). Aqui, ele liga duas empresas escolhidas pelo
consumidor, com as mesmas consultas de ``cypher/03_multi_hop.cypher``:

- societário: só ``PARTICIPA_DE`` (Empresa ← Socio → Empresa);
- estrutural: tipos do domínio, exceto ``ORIGINADO_DE`` (que ligaria quaisquer empresas pela Fonte).

Cada consulta devolve no máximo um caminho e no máximo ``max_hops`` relacionamentos (até 6), para
o subgrafo continuar pequeno. Nenhum caminho é prova de vínculo jurídico: o caminho por CNAE indica
só atividade econômica declarada em comum, e ``MENCIONA`` é citação textual candidata.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence

from .retrieval import MENCIONA_WARNING, _primary_label, node_payload, path_to_text

MAX_HOPS = 6
SOCIETARIO_TYPES = ("PARTICIPA_DE",)
ESTRUTURAL_TYPES = ("PARTICIPA_DE", "POSSUI_ESTABELECIMENTO", "EXERCE_CNAE", "APLICADA_A", "EXTRATO_DE", "MENCIONA")

CNAE_WARNING = (
    "Caminho por CNAE indica apenas atividade econômica declarada em comum; não é vínculo "
    "societário, de controle ou comercial."
)

EXISTS_QUERY = """
UNWIND $ids AS id
OPTIONAL MATCH (e:Empresa {cnpj_basico: id})
RETURN id, e IS NOT NULL AS existe
""".strip()


def shortest_path_query(rel_types: Sequence[str], max_hops: int) -> str:
    """Consulta parametrizada; tipos e limite vêm de constantes validadas, não do usuário."""
    return f"""
MATCH (a:Empresa {{cnpj_basico: $cnpj_a}}), (b:Empresa {{cnpj_basico: $cnpj_b}})
WHERE a <> b
MATCH p = shortestPath((a)-[:{'|'.join(rel_types)}*..{max_hops}]-(b))
RETURN [n IN nodes(p) | {{element_id: elementId(n), labels: labels(n),
          properties: n {{.*, embedding: null, texto: null, mencoes_json: null}}}}] AS nodes,
       [r IN relationships(p) | {{element_id: elementId(r), type: type(r),
          start: elementId(startNode(r)), end: elementId(endNode(r)), properties: properties(r)}}] AS relationships
""".strip()


def classify_path(path: Dict[str, Any]) -> str:
    """``societario`` | ``mencao_candidata`` | ``atividade_cnae`` | ``estrutural``."""
    types = [rel["type"] for rel in path["relationships"]]
    labels = {_primary_label(node.get("labels") or [])[0] for node in path["nodes"][1:-1]}
    if types and all(t == "PARTICIPA_DE" for t in types):
        return "societario"
    if "MENCIONA" in types:
        return "mencao_candidata"
    if "CNAE" in labels:
        return "atividade_cnae"
    return "estrutural"


def _validate(cnpj_a: Any, cnpj_b: Any, max_hops: Any) -> tuple:
    if not isinstance(cnpj_a, str) or not isinstance(cnpj_b, str) or not cnpj_a.strip() or not cnpj_b.strip():
        raise ValueError("Informe dois cnpj_basico como texto não vazio.")
    cnpj_a, cnpj_b = cnpj_a.strip(), cnpj_b.strip()
    if cnpj_a == cnpj_b:
        raise ValueError("As duas empresas precisam ser diferentes.")
    if isinstance(max_hops, bool) or not isinstance(max_hops, int) or not 1 <= max_hops <= MAX_HOPS:
        raise ValueError(f"max_hops precisa ser um inteiro entre 1 e {MAX_HOPS}.")
    return cnpj_a, cnpj_b


def find_company_paths(session: Any, cnpj_a: str, cnpj_b: str, max_hops: int = MAX_HOPS) -> Dict[str, Any]:
    """Caminhos mínimos societário e estrutural entre duas empresas.

    ``session`` pode ser uma sessão ou transação do driver (qualquer objeto com ``run``).
    """
    cnpj_a, cnpj_b = _validate(cnpj_a, cnpj_b, max_hops)
    queries = {
        "societario": shortest_path_query(SOCIETARIO_TYPES, max_hops),
        "estrutural": shortest_path_query(ESTRUTURAL_TYPES, max_hops),
    }
    result: Dict[str, Any] = {
        "empresas": [cnpj_a, cnpj_b],
        "max_hops": max_hops,
        "paths": [],
        "nodes": [],
        "relationships": [],
        "cypher": "\n\n".join(f"// Caminho {name}\n{query};" for name, query in queries.items()),
        "warnings": [],
    }
    missing = [r["id"] for r in session.run(EXISTS_QUERY, {"ids": [cnpj_a, cnpj_b]}) if not r["existe"]]
    if missing:
        result["warnings"].append(f"Empresa(s) não encontrada(s) no grafo: {', '.join(missing)}.")
        return result

    params = {"cnpj_a": cnpj_a, "cnpj_b": cnpj_b}
    found: Dict[str, Dict[str, Any]] = {}
    for name, query in queries.items():
        record = next(iter(session.run(query, params)), None)
        if record is not None:
            found[name] = {"nodes": record["nodes"], "relationships": record["relationships"]}

    nodes: Dict[str, Dict[str, Any]] = {}
    relationships: Dict[str, Dict[str, Any]] = {}
    signatures = set()
    for name in ("societario", "estrutural"):
        path = found.get(name)
        if path is None:
            continue
        signature = tuple(rel["element_id"] for rel in path["relationships"])
        if signature in signatures:
            continue  # o caminho estrutural mínimo pode ser o próprio caminho societário
        signatures.add(signature)
        ids = {}
        for node in path["nodes"]:
            payload = node_payload(node)
            ids[node["element_id"]] = payload["id"]
            nodes.setdefault(payload["id"], payload)
        for rel in path["relationships"]:
            relationships.setdefault(rel["element_id"], {
                "source": ids[rel["start"]], "target": ids[rel["end"]],
                "type": rel["type"], "properties": dict(rel.get("properties") or {}),
            })
        result["paths"].append({
            "kind": classify_path(path),
            "length": len(path["relationships"]),
            "nodes": [ids[node["element_id"]] for node in path["nodes"]],
            "relationship_types": [rel["type"] for rel in path["relationships"]],
            "text": path_to_text(path, ids),
        })

    result["nodes"] = list(nodes.values())
    result["relationships"] = list(relationships.values())
    kinds = {path["kind"] for path in result["paths"]}
    if "societario" not in kinds:
        result["warnings"].append(
            f"Nenhum caminho societário (sócio em comum) entre {cnpj_a} e {cnpj_b} com até {max_hops} "
            "relacionamentos no grafo. A ausência no recorte não prova ausência na base completa."
        )
    if not result["paths"]:
        result["warnings"].append(f"Nenhum caminho com até {max_hops} relacionamentos entre {cnpj_a} e {cnpj_b}.")
    if "atividade_cnae" in kinds:
        result["warnings"].append(CNAE_WARNING)
    if "mencao_candidata" in kinds:
        result["warnings"].append(MENCIONA_WARNING)
    return result
