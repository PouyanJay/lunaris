from pydantic import Field

from ...graph.schema.base import LiveModel
from .director_move import DirectorMove


class SessionTurn(LiveModel):
    """One beat of the loop: what the director chose, and what the tutor said about it.

    The turn is the unit that gets a row, so the director's trace and the learner's transcript are
    the same sequence read two ways (A2) — which is what stops them ever disagreeing about what
    happened. Later tasks add the learner's answer and its grade to this same record.
    """

    #: 1-based, monotonic within a session. The order the learner lived it.
    seq: int = Field(ge=1)
    move: DirectorMove
    #: What the tutor said, in the learner's language. Empty is never valid: a turn the learner
    #: cannot see is a decision that happened to them invisibly.
    tutor: str = Field(min_length=1)
    #: The run that produced this turn (R6) — the session's id answers "show me this learner's
    #: session", this one answers "show me what the tutor was actually asked on this line". A turn
    #: is one or more model calls, so without it a stored transcript is unattached to the logs that
    #: explain it.
    run_id: str = Field(min_length=1, max_length=100)
