import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELATIONSHIP_TYPES = {
    "equivalent", "related", "broader", "narrower", "complementary",
    "partially_addresses",
}


def load_crosswalk(path=None):
    source = Path(path) if path else ROOT / "data" / "config" / "standards_crosswalk_sample.json"
    with source.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def claim_matches(claim, selector):
    return all(claim.get(field) in accepted for field, accepted in selector.items())


def apply_crosswalk(graph, claims, crosswalk):
    """Return an augmented graph; unverified mappings remain config-only."""
    result = copy.deepcopy(graph)
    nodes = {node["id"]: node for node in result["nodes"]}
    edges = list(result["edges"])
    edge_keys = {
        (edge["source"], edge["target"], edge["label"], edge.get("mapping_id"))
        for edge in edges
    }
    concepts = {concept["concept_id"]: concept for concept in crosswalk["concepts"]}

    for concept in concepts.values():
        matching_claims = [c for c in claims if claim_matches(c, concept["claim_match"])]
        if not matching_claims:
            continue
        concept_node_id = "concept:" + concept["concept_id"]
        concept_node = {
            "id": concept_node_id,
            "type": "CanonicalConcept",
            "label": concept["name"],
            "concept_id": concept["concept_id"],
        }
        if concept.get("description"):
            concept_node["details"] = concept["description"]
        nodes[concept_node_id] = concept_node
        for claim in matching_claims:
            edge = {
                "source": "claim:" + claim["claim_id"],
                "target": concept_node_id,
                "label": "HAS_CONCEPT",
            }
            key = (edge["source"], edge["target"], edge["label"], None)
            if key not in edge_keys:
                edges.append(edge)
                edge_keys.add(key)

    for mapping in crosswalk["mappings"]:
        if mapping["verification_status"] != "verified":
            continue
        if mapping["relationship_type"] not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unsupported relationship type: {mapping['relationship_type']}")
        concept_node_id = "concept:" + mapping["concept_id"]
        if concept_node_id not in nodes:
            continue
        standard_node_id = "standard:" + mapping["reference_id"]
        nodes.setdefault(standard_node_id, {
            "id": standard_node_id,
            "type": "StandardReference",
            "label": f"{mapping['reference_code']} · {mapping['reference_title']}",
            "reference_code": mapping["reference_code"],
            "reference_title": mapping["reference_title"],
            "standard_name": mapping["standard_name"],
            "standard_version": mapping["standard_version"],
            "source_type": mapping["source_type"],
            "source_document": mapping["source_document"],
            "source_url": mapping["source_url"],
            "verification_status": "verified",
            "disclaimer": "Crosswalk relationship only; not a compliance or violation conclusion.",
        })
        edge = {
            "source": concept_node_id,
            "target": standard_node_id,
            "label": "MAPPED_TO",
            "mapping_id": mapping["mapping_id"],
            "relationship_type": mapping["relationship_type"],
            "mapping_reason": mapping["mapping_reason"],
            "verification_status": "verified",
        }
        for field in ("covered_aspects", "unverified_aspects", "industry_applicability_status"):
            if field in mapping:
                edge[field] = mapping[field]
        key = (edge["source"], edge["target"], edge["label"], edge["mapping_id"])
        if key not in edge_keys:
            edges.append(edge)
            edge_keys.add(key)

    result["nodes"] = list(nodes.values())
    result["edges"] = edges
    return result
