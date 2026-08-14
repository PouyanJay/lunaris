from lunaris_live.graph.schema.base import LiveModel
from lunaris_live.session import Session, SessionStatus, TurnGrade
from pydantic import Field


class SessionSnapshot(LiveModel):
    """Where a session stands, as the state channel of an AG-UI run carries it.

    The counterpart of the text frames rather than a copy of them. Text is what the learner reads;
    this is what a surface renders *around* it — which turn a component belongs to, what that turn
    asks for, how the last answer was judged, and whether the session is still taking answers. T3's
    Tier 1 components are written against this, so it is a contract and not a debug payload.

    Deliberately a projection and not the ``Session`` itself. The session carries every turn of a
    forty-minute sitting, and re-sending all of it on every run would put the transcript on the wire
    once per turn to say one thing has changed. It is also the wrong shape for the job: a surface
    asking "what is being asked right now" should not have to know that the answer is the last
    element of a list, and ``GET /{id}`` remains the way to read the whole thing (U2).
    """

    session_id: str = Field(min_length=1, max_length=100)
    status: SessionStatus
    #: The turn now in front of the learner. 0 only for a session with no turns at all, which is a
    #: state ``open_session`` cannot produce and a stored row could still be in.
    turn: int = Field(ge=0)
    #: The do-statement that turn stages, in the concept's own words (U1). ``None`` when the concept
    #: has nothing a text session can check — a surface must then offer a place to think, not a
    #: place to be marked.
    criterion: str | None = None
    #: The verdict on the most recent answer that was scored. ``None`` means nothing has been judged
    #: yet, never "judged and failed" — the distinction the whole learner model rests on.
    grade: TurnGrade | None = None

    @classmethod
    def of(cls, session: Session) -> "SessionSnapshot":
        """Read the state off a session.

        The grade is the last one *recorded*, not the last turn's: the turn in front of the learner
        has not been answered yet, so its grade is always ``None``, and a surface reading it there
        would show a blank verdict the instant the tutor finished speaking about the answer that
        earned one.
        """
        standing = session.turns[-1] if session.turns else None
        graded = next((turn.grade for turn in reversed(session.turns) if turn.grade), None)
        return cls(
            session_id=session.session_id,
            status=session.status,
            turn=standing.seq if standing else 0,
            criterion=standing.criterion.statement
            if standing and standing.criterion is not None
            else None,
            grade=graded,
        )
