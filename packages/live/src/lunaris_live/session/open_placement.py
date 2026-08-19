from datetime import UTC, datetime

import structlog

from .interviewer_unavailable_error import InterviewerUnavailableError
from .protocols import IInterviewer
from .schema import DirectorMove, MoveKind, Session, SessionStatus, SessionTurn
from .stub_interviewer import StubInterviewer

logger = structlog.get_logger()

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

    An interviewer that cannot open (down, timed out, nothing to ask) does not stop the session
    opening: by the time it is asked, the caller has launched the compile, and a session that
    failed at the door would leave a compile running for nobody. The opening question is then the
    plain one the offline path asks, and the interview goes on from there or ends on the next turn.
    """
    question = await _opening_question(interviewer, topic, run_id=run_id)
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


async def _opening_question(interviewer: IInterviewer, topic: str, *, run_id: str) -> str:
    """The first question, or the plain one when the interviewer cannot give its own."""
    try:
        question = await interviewer.ask(topic, exchanges=(), run_id=run_id)
    except InterviewerUnavailableError:
        logger.warning(
            "live.placement.interviewer_unavailable_at_open", run_id=run_id, exc_info=True
        )
        question = None
    if question is None:
        # ``None`` at the door is "nothing to ask" from an interviewer that has heard nothing, which
        # is a broken interviewer rather than a finished interview; the plain question stands in.
        question = await StubInterviewer().ask(topic, run_id=run_id)
    assert question is not None, "the offline interviewer always has an opening question"
    return question
