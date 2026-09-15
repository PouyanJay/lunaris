import asyncio

import structlog
from lunaris_live.graph import IGraphStore
from lunaris_live.session import ISessionStore, Session
from lunaris_live.session.schema import SessionStatus
from lunaris_live.voice.error import VoiceError

from ..corpus.check_graph_source import check_graph_source
from ..corpus.protocols.access_guard import ICorpusAccessGuard
from ..work_refused import LiveWorkRefusedError


class StoredVoiceSessions:
    """A source read cannot close, grade or otherwise mutate the learning session."""

    def __init__(
        self,
        sessions: ISessionStore,
        *,
        graphs: IGraphStore | None = None,
        source_access: ICorpusAccessGuard | None = None,
    ) -> None:
        self._sessions = sessions
        self._graphs = graphs
        self._source_access = source_access

    async def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        if self._graphs is not None:
            try:
                graph = await asyncio.to_thread(
                    self._graphs.load, session.graph_id, owner_id=owner_id
                )
            except FileNotFoundError:
                if session.status in (SessionStatus.PLACING, SessionStatus.WARMING):
                    return session
                raise
            try:
                await check_graph_source(graph, self._source_access, owner_id)
            except LiveWorkRefusedError as exc:
                raise VoiceError(exc.detail, status_code=exc.status_code) from exc
        structlog.get_logger().info("live.voice.source_loaded", session_id=session_id)
        return session
