import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from lunaris_live.corpus.schemas.asset import NodeAsset
from lunaris_live.graph import ConceptGraph
from lunaris_live.session import Session
from lunaris_live.session.schema import SessionStatus
from lunaris_runtime.persistence import VideoArtifactPaths

from .media_stale import MaterialStaleError
from .media_unavailable import MaterialUnavailableError
from .models.media_request import CorpusMediaRequest
from .models.media_services import CorpusMediaServices
from .schemas.media_url import MediaUrl


def _standing_asset(session: Session, asset_id: str, turn: int) -> NodeAsset:
    if not session.turns or session.turns[-1].seq != turn or session.turns[-1].answer is not None:
        raise MaterialStaleError
    matches = [asset for asset in session.turns[-1].materials if asset.asset_id == asset_id]
    if len(matches) != 1:
        raise MaterialUnavailableError
    return matches[0]


def _verified_asset(graph: ConceptGraph, session: Session, asset: NodeAsset) -> None:
    source = graph.corpus
    node_id = session.turns[-1].move.node_id
    matches = [
        candidate
        for node in graph.nodes
        if node.id == node_id
        for candidate in node.assets
        if candidate.asset_id == asset.asset_id
    ]
    if (
        source is None
        or source.status != "verified"
        or asset.origin != "ingested"
        or asset.kind != "video_clip"
        or asset.clip is None
        or asset.verification is None
        or asset.source_digest != source.digest
        or asset.verification.source_digest != source.digest
        or len(matches) != 1
        or matches[0] != asset
    ):
        raise MaterialUnavailableError


class CorpusMediaResolver:
    """Sign only a current verified clip, using entirely read-only session/source checks."""

    def __init__(
        self,
        services: CorpusMediaServices,
        *,
        session_budget_s: float,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions = services.sessions
        self._graphs = services.graphs
        self._access = services.source_access
        self._inventory = services.inventory
        self._storage = services.storage
        self._budget = session_budget_s
        self._clock = clock or (lambda: datetime.now(UTC))

    async def _session(self, session_id: str, owner_id: str) -> Session:
        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        if session.status != SessionStatus.ACTIVE or session.started_at.tzinfo is None:
            raise MaterialStaleError
        elapsed = (self._clock() - session.started_at).total_seconds()
        if not 0 <= elapsed < self._budget:
            raise MaterialStaleError
        return session

    async def resolve(self, request: CorpusMediaRequest) -> MediaUrl:
        session = await self._session(request.session_id, request.owner_id)
        asset = _standing_asset(session, request.asset_id, request.turn)
        graph = await asyncio.to_thread(
            self._graphs.load, session.graph_id, owner_id=request.owner_id
        )
        await self._access.check(graph, owner_id=request.owner_id, run_id=request.run_id)
        _verified_asset(graph, session, asset)
        assert graph.corpus is not None and asset.clip is not None
        inventory = await self._inventory.load(
            graph.corpus.course_id, owner_id=request.owner_id, run_id=request.run_id
        )
        if asset.clip not in inventory.clips:
            raise MaterialUnavailableError
        current = await self._session(request.session_id, request.owner_id)
        if _standing_asset(current, request.asset_id, request.turn) != asset:
            raise MaterialStaleError
        await self._access.check(graph, owner_id=request.owner_id, run_id=request.run_id)
        path = VideoArtifactPaths.for_coordinates(
            request.owner_id, graph.corpus.course_id, asset.clip.job_id
        ).mp4
        url = await self._storage.signed_url(path=path, expires_in_seconds=60)
        return MediaUrl(url=url)
