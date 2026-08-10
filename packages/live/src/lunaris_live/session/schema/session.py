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
    turns: list[SessionTurn] = Field(default_factory=list)
