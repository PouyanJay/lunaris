import json

from ...graph.schema import ConceptNode, MasteryCriterion
from ..content_hash import content_hash
from .models.versions import SimVersions


def sim_cache_key(
    node: ConceptNode,
    criterion: MasteryCriterion,
    *,
    versions: SimVersions | None = None,
) -> str:
    """Teaching identity excludes transient map/node IDs; scope is enforced separately."""
    versions = versions or SimVersions()
    context = {
        "name": node.name,
        "definition": node.definition,
        "aliases": sorted(node.aliases),
        "mastery_criteria": [item.model_dump(mode="json") for item in node.mastery_criteria],
        "teaching_spec": node.teaching_spec.model_dump(mode="json") if node.teaching_spec else None,
        "criterion": criterion.model_dump(mode="json"),
        "factory_version": versions.factory,
        "verifier_version": versions.verifier,
        "contract_version": versions.contract,
    }
    return content_hash(json.dumps(context, sort_keys=True, separators=(",", ":")))
