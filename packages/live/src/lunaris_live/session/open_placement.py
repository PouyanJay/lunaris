from datetime import UTC, datetime

from .protocols import IInterviewer
from .schema import DirectorMove, MoveKind, Session, SessionStatus, SessionTurn

#: Why the first turn is a question rather than a lesson, in the words a trace reader gets. Every
#: other move's reason is the director's; this one is the loop's, because there is no director yet.
_REASON = "The map is still being built, so the first minutes are about you, not about it."


async def open_placement(
    topic: str,
    *,
    graph_id: str,
    session_id: str,
    run_id: str,
    interviewer: IInterviewer,
) -> Session:
    """Open a session on a topic whose map is still compiling, and ask the first question.

    The counterpart of ``open_session`` for the moment before there is a map (plan §6): the compile
    has been launched under ``graph_id`` by the caller, and the learner is not made to watch it.
    What comes back is the same ``Session`` the loop persists — status ``PLACING``, one turn of kind
    ``PLACE`` — so every surface and every store treats a placement as the beginning of a session
    rather than as a second kind of thing that later has to be stitched to the first.

    Raises whatever the interviewer raises: a placement whose first question could not be asked is
    not a session, exactly as an opening whose first turn could not be taught is not (P2a).
    Raises ``ValueError`` if the interviewer has nothing to ask on an empty interview, which is a
    broken interviewer rather than a finished interview.
    """
    question = await interviewer.ask(topic, exchanges=(), graph_has_landed=False, run_id=run_id)
    if question is None:
        raise ValueError("an interviewer with nothing to ask cannot open a placement")
    return Session(
        session_id=session_id,
        graph_id=graph_id,
        topic=topic,
        status=SessionStatus.PLACING,
        # Stamped once, here, at the only moment a session is born (P2a AD20). The interview is
        # inside the session's clock, not before it (A1).
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.PLACE, reason=_REASON),
                tutor=question,
                run_id=run_id,
            )
        ],
    )
