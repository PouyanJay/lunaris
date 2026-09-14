from typing import Protocol

from ...session.schema import Session


class IVoiceSessionReader(Protocol):
    async def load(self, session_id: str, *, owner_id: str | None = None) -> Session: ...
