from typing import Protocol

from ..schema import Session


class ISessionStore(Protocol):
    """Persistence for a learner's sessions.

    Synchronous because the durable implementation is supabase-py, which is; callers hop it to a
    thread rather than this protocol pretending to be async. Mirrors ``IGraphStore`` exactly, for
    the same reason it did: the in-memory and Supabase implementations have to be substitutable
    without a caller knowing which it has.

    ``owner_id`` is the authenticated learner. ``load`` raises ``FileNotFoundError`` when there is
    no such session **for that owner** — another learner's session is not-found rather than
    forbidden, because its existence is itself owner-scoped information.
    """

    def save(self, session: Session, *, owner_id: str | None = None) -> None: ...

    def load(self, session_id: str, *, owner_id: str | None = None) -> Session: ...
