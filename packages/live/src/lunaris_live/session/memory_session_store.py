import threading
from datetime import UTC, datetime
from itertools import count

from .schema import Session, SessionStatus, SessionSummary
from .stale_answer_error import StaleAnswerError

#: The statuses a session is done in. Nothing more is taught, and nothing more will be written.
_FINISHED = frozenset({SessionStatus.CLOSED, SessionStatus.ABANDONED})


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
        # When each session last moved, and in what order. The wall clock is what a learner reads;
        # the counter is what the list is ordered by, because two saves inside one clock tick would
        # otherwise come back in an order nothing decided. The durable store gets this from
        # Postgres and its ``updated_at`` column instead.
        self._touched: dict[str, tuple[int, datetime]] = {}
        self._ticks = count()
        # The service hops these calls onto worker threads, so two answers in flight really are two
        # threads. The lock makes the check and the write one step; without it the compare-and-set
        # below is a race with a smaller window rather than a guarantee.
        self._lock = threading.Lock()

    def save(
        self, session: Session, *, owner_id: str | None = None, expect_turns: int | None = None
    ) -> None:
        with self._lock:
            if expect_turns is not None:
                stored = self._sessions.get(session.session_id)
                if stored is not None and len(stored.turns) != expect_turns:
                    raise StaleAnswerError(
                        f"session {session.session_id} has moved on to {len(stored.turns)} turns"
                    )
            self._sessions[session.session_id] = session
            self._owners[session.session_id] = owner_id
            self._touched[session.session_id] = (next(self._ticks), datetime.now(UTC))

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

    def has_open_on(self, graph_id: str, *, owner_id: str | None = None) -> bool:
        with self._lock:
            return any(
                session.graph_id == graph_id and session.status not in _FINISHED
                for session_id, session in self._sessions.items()
                if self._owners.get(session_id) == owner_id
            )

    def delete(self, session_id: str, *, owner_id: str | None = None) -> None:
        with self._lock:
            # Scoped exactly as ``load`` is, and checked before anything is removed: an unscoped
            # delete must not be able to reach an owned session, and a wrong owner must not be
            # able to learn that the id exists by watching what the call does.
            if self._owners.get(session_id) != owner_id or session_id not in self._sessions:
                raise FileNotFoundError(session_id)
            del self._sessions[session_id]
            del self._owners[session_id]
            self._touched.pop(session_id, None)

    def recent(self, *, owner_id: str | None = None, limit: int = 50) -> list[SessionSummary]:
        with self._lock:
            mine = [
                (self._touched[session_id], session)
                for session_id, session in self._sessions.items()
                # Exact match, for the reason ``load`` gives at length: an unscoped read must not
                # be able to reach an owned session because two config flags happen to agree.
                if self._owners.get(session_id) == owner_id
            ]
        mine.sort(key=lambda pair: pair[0][0], reverse=True)
        return [_summary_of(session, moved_at=at) for (_, at), session in mine[:limit]]


def _summary_of(session: Session, *, moved_at: datetime) -> SessionSummary:
    return SessionSummary(
        session_id=session.session_id,
        graph_id=session.graph_id,
        topic=session.topic,
        status=session.status,
        turn_count=len(session.turns),
        started_at=session.started_at,
        updated_at=moved_at,
    )
