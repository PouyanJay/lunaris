from ..corpus.schemas.asset import NodeAsset
from ..graph.schema import ConceptNode
from .schema.move_kind import MoveKind


def supporting_assets(node: ConceptNode, kind: MoveKind) -> list[NodeAsset]:
    """Materials support teaching; retrieval gets no answer-revealing source excerpts."""
    if kind is MoveKind.RETRIEVE:
        return []
    return [
        asset
        for asset in node.assets
        if asset.verification is not None
        and asset.verification.source_digest == asset.source_digest
    ][:4]
