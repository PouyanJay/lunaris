from uuid import UUID

from ...graph.schema import ConceptNode, MasteryCriterion
from ...session.schema import SimApp
from .cache_key import sim_cache_key
from .schema.asset import SimAsset


class PreloadedSimRegistry:
    """Per-request snapshot: no I/O or generation in the synchronous session lookup."""

    def __init__(self, assets: list[SimAsset], *, owner_id: str | None) -> None:
        owner = UUID(owner_id) if owner_id else None
        self._assets = {
            asset.cache_key: SimAsset.model_validate_json(asset.model_dump_json())
            for asset in assets
            if not asset.revoked and (asset.public_source is not None or asset.owner_id == owner)
        }

    def app_for(self, node: ConceptNode, criterion: MasteryCriterion) -> SimApp | None:
        asset = self._assets.get(sim_cache_key(node, criterion))
        if asset is None or asset.bundle.spec.contract.objective != criterion.statement:
            return None
        return SimApp(
            app_id=str(asset.id),
            url=f"/api/live/sims/assets/{asset.id}",
            title=node.name,
            contract=asset.bundle.spec.contract.model_copy(deep=True),
        )
