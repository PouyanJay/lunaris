import asyncio
from uuid import uuid4

import structlog

from ...graph import ConceptGraph
from ...session import ISimRegistry, node_of
from ..registry.cache_key import sim_cache_key
from ..registry.preloaded_registry import PreloadedSimRegistry
from ..registry.protocols.asset_store import ISimAssetStore
from .models.preparation import SimPreparation
from .protocols.queue import ISimQueue
from .schema.request import SimRequest


class SimMaterials:
    """Load approved references without paid work; enqueue one missing instrument after a turn."""

    def __init__(self, assets: ISimAssetStore, queue: ISimQueue) -> None:
        self._assets, self._queue = assets, queue

    async def load(self, graph: ConceptGraph, *, owner_id: str | None) -> ISimRegistry:
        keys = [
            sim_cache_key(node, c)
            for node in graph.nodes
            for c in node.mastery_criteria
            if c.needs_sim
        ]
        assets = []
        for start in range(0, len(keys), 100):
            assets.extend(
                await asyncio.to_thread(
                    self._assets.find, keys[start : start + 100], owner_id=owner_id
                )
            )
        return PreloadedSimRegistry(assets, owner_id=owner_id)

    def _request(self, graph: ConceptGraph, node_id: str) -> SimRequest | None:
        node = node_of(graph, node_id)
        if node is None or any(not c.needs_sim for c in node.mastery_criteria):
            return None
        criterion = next(iter(node.mastery_criteria), None)
        return SimRequest(node=node, criterion=criterion, run_id=uuid4().hex) if criterion else None

    async def prepare(self, preparation: SimPreparation) -> None:
        graph, node_id = preparation.graph, preparation.node_id
        session_id, owner_id = preparation.session_id, preparation.owner_id
        request = self._request(graph, node_id)
        if request is None or owner_id is None:
            return
        try:
            assets = await asyncio.to_thread(
                self._assets.find,
                [sim_cache_key(request.node, request.criterion)],
                owner_id=owner_id,
            )
            if assets:
                return
            status = await asyncio.to_thread(
                self._queue.enqueue, request, session_id=session_id, owner_id=owner_id
            )
            structlog.get_logger().info(
                "live.sim.prefetch",
                node=node_id,
                status=status,
                session_id=session_id,
                run_id=request.run_id,
            )
        except Exception:
            structlog.get_logger().warning("live.sim.prefetch_unavailable", node=node_id)

    async def status(self, graph: ConceptGraph, node_id: str, *, owner_id: str | None) -> str:
        request = self._request(graph, node_id)
        if request is None or owner_id is None:
            return "unavailable"
        registry = await self.load(graph, owner_id=owner_id)
        if registry.app_for(request.node, request.criterion):
            return "approved"
        return await asyncio.to_thread(
            self._queue.status, sim_cache_key(request.node, request.criterion), owner_id=owner_id
        )
