from .schema import Session


class MemorySessionStore:
    """In-process session store — offline dev and the suite.

    A singleton in the composition root, like ``MemoryGraphStore``: opening a session and the next
    turn of it are separate requests, so a per-request store would lose the session between them.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        # Kept parallel to the sessions so ``Session`` stays a clean wire contract with no owner
        # field on it — the same split the in-memory cost store uses.
        self._owners: dict[str, str | None] = {}

    def save(self, session: Session, *, owner_id: str | None = None) -> None:
        self._sessions[session.session_id] = session
        self._owners[session.session_id] = owner_id

    def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise FileNotFoundError(session_id)
        # Exact match, so an *unscoped* read cannot reach an owned session either. Treating
        # ``owner_id=None`` as "see everything" would be safe only while auth stays unconfigured —
        # a property of two config flags agreeing, not of this store. It refuses on its own terms,
        # the same rule ``MemoryGraphStore`` settled in Phase 1, and it matters more here: a
        # session is a transcript of somebody being taught, not a map of a subject.
        if self._owners.get(session_id) != owner_id:
            raise FileNotFoundError(session_id)
        return session
