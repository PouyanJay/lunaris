from collections.abc import Mapping, Sequence

from ...graph.schema import ConceptGraph
from ..schemas.asset import NodeAsset
from .models.request import MappingRequest
from .schemas.report import MappingReport


def mapping_result(
    request: MappingRequest, report: MappingReport, assets: Mapping[str, Sequence[NodeAsset]]
) -> ConceptGraph:
    """Only the composition root may publish readiness after all reports agree."""
    source = request.graph.corpus
    if source is not None and source.status != "failed":
        source = source.model_copy(update={"status": "pending"})
    return request.graph.model_copy(
        update={
            "corpus": source,
            "mapping_report": report,
            "nodes": [
                node.model_copy(update={"assets": list(assets.get(node.id, ()))})
                for node in request.graph.nodes
            ],
        }
    )
