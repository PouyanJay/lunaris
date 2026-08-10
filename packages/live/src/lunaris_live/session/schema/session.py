from datetime import datetime

from pydantic import Field

from ...graph.schema.base import LiveModel
from .session_status import SessionStatus
from .session_turn import SessionTurn


class Session(LiveModel):
    """A learner's run at a concept graph: the turns so far, and whether it is still going.

    Persisted rather than held on a connection (U2). A session is 25-40 minutes of accumulated
    context about one learner, and a page reload must not be able to destroy it — the same lesson
    Phase 1 learned when a dropped stream nearly cancelled a three-minute compile (AD12).

    The graph is referenced, never embedded: it is mutable (C1 grows it mid-session), so a copy
    taken at session start would be stale the first time the learner asked something off the map.
    """

    session_id: str = Field(min_length=1, max_length=100)
    graph_id: str = Field(min_length=1, max_length=100)
    status: SessionStatus = SessionStatus.ACTIVE
    #: When the session opened, in UTC. The budget is wall time (plan §6, AD9), and wall time is the
    #: one thing a resumed session cannot recover from its own turns — so it is stamped here and
    #: carried in the row rather than held in the process, which a reload would reset.
    #:
    #: Required, with no default, and that is the load-bearing part. A default would run afresh on
    #: every parse, so a row stored before this field existed would be re-stamped "now" on each
    #: read — handing a session that was one turn from its budget a whole new one, every time it
    #: was reloaded. Unreadable is the honest answer for a session nobody can date: it surfaces as
    #: ``SessionFormatError`` (a 500 that says so) rather than as an unbounded session.
    started_at: datetime
    turns: list[SessionTurn] = Field(default_factory=list)
