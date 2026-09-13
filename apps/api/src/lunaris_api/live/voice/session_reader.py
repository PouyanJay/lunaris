import asyncio

import structlog
from lunaris_live.session import ISessionStore, Session


class StoredVoiceSessions:
    """A source read cannot close, grade or otherwise mutate the learning session."""

    def __init__(self, sessions: ISessionStore) -> None:
        self._sessions = sessions

    async def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
        session = await asyncio.to_thread(self._sessions.load, session_id, owner_id=owner_id)
        structlog.get_logger().info("live.voice.source_loaded", session_id=session_id)
        return session
