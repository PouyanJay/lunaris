from datetime import datetime

from pydantic import Field

from ...graph.schema.base import LiveModel
from .session_status import SessionStatus


class SessionSummary(LiveModel):
    """One session as a list shows it: enough to recognise, far too little to resume from.

    Its own contract rather than a trimmed ``Session`` because the two are read for opposite
    reasons. A session is always read whole when it is being *lived* (the transcript is the state),
    and a learner looking over their sessions wants none of that: sending twenty full transcripts to
    draw twenty rows would put a learner's entire teaching history on the wire to render a list.

    Every field here is one a learner can act on. ``topic`` is what they recognise it by, ``status``
    is whether it is still going, ``turn_count`` is how far they got, and ``updated_at`` is what the
    list is ordered by (the column ``live_sessions_user_idx`` has indexed since Phase 2a).
    """

    session_id: str = Field(min_length=1, max_length=100)
    graph_id: str = Field(min_length=1, max_length=100)
    #: ``None`` only for a session opened on a map that carried no topic, which the compiler does
    #: not produce. Optional rather than required so one unnameable row cannot break the whole list.
    topic: str | None = Field(default=None, min_length=1, max_length=500)
    status: SessionStatus
    turn_count: int = Field(ge=0)
    started_at: datetime
    #: When the session last moved, which is what "newest first" means to a learner: the one they
    #: were last doing, not the one they first opened.
    updated_at: datetime
