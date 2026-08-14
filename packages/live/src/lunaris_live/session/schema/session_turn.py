from pydantic import Field

from ...graph.schema.base import LiveModel
from ...graph.schema.mastery_criterion import MasteryCriterion
from ..max_answer_chars import MAX_ANSWER_CHARS
from .director_move import DirectorMove
from .surface_spec import SurfaceSpec
from .turn_grade import TurnGrade


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
    #: The do-statement the tutor put in front of the learner, copied onto the turn rather than
    #: referenced: C1 lets the map change mid-session, so a transcript pointing at a node id could
    #: come to misreport what somebody was actually asked. ``None`` when the concept's only criteria
    #: need a simulator (Phase 3) — taught here, not checkable here.
    criterion: MasteryCriterion | None = None
    #: What the learner said, in their words. ``None`` until they answer, which is also what makes
    #: "the turn in front of them" the last one with no answer.
    answer: str | None = Field(default=None, max_length=MAX_ANSWER_CHARS)
    #: What that answer was judged to show. ``None`` when nothing was staged to judge it against —
    #: never a stand-in for "we could not tell", which leaves the turn ungraded rather than failed.
    grade: TurnGrade | None = None
    #: The Tier 1 component this turn put on screen, and its props (P2b T3). Recorded rather than
    #: re-derived on read, so a reloaded tab renders the card the learner was halfway through
    #: answering — and so the trace says what they were actually shown, not what today's rules would
    #: show them now.
    #:
    #: Optional because every session row written before P2b has none (R4). Required would make the
    #: whole of Live's stored history unreadable, which is the failure ``SessionFormatError`` exists
    #: to report about a corrupt row rather than about us.
    surface: SurfaceSpec | None = None
