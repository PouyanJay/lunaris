from collections.abc import Mapping

import structlog

from ..graph import ConceptGraph
from .exchanges_of import exchanges_of
from .interviewer_unavailable_error import InterviewerUnavailableError
from .protocols import IInterviewer, IPriorMapper, ISimRegistry, ITutor, ITutorDeltaSink
from .schema import (
    DirectorMove,
    InterviewExchange,
    LearnerModel,
    LessonParts,
    MoveKind,
    Session,
    SessionStatus,
    SessionTurn,
)
from .session_closed_error import SessionClosedError
from .settle_placement import settle_placement
from .stale_answer_error import StaleAnswerError
from .turn_outcome import TurnOutcome

logger = structlog.get_logger()

#: The most the interview may ask before it stops on its own (A2), unless the caller says
#: otherwise. A compile's worth of waiting is the plan's budget for it (§6), and a compile is
#: under a minute in practice; four is what a learner can answer in that time without the
#: interview becoming the session. The API reads its own setting for it (T8).
DEFAULT_MAX_QUESTIONS = 4

#: What the learner reads when the interview has ended and the map has not landed (WARMING). Asks
#: nothing, on purpose: the surface polls, and an answer here would have nothing to be an answer to.
_WARMING = (
    "Thanks, that's what I needed. The map of {topic} is nearly ready; I'll start the moment it is."
)


async def take_placement_turn(
    session: Session,
    *,
    answer: str,
    answering_seq: int,
    interviewer: IInterviewer,
    mapper: IPriorMapper,
    graph: ConceptGraph | None,
    failure: str | None,
    model: LearnerModel,
    tutor: ITutor,
    run_id: str,
    elapsed_s: float,
    budget_s: float,
    on_delta: ITutorDeltaSink | None = None,
    sims: ISimRegistry | None = None,
    prefetched: Mapping[str, LessonParts] | None = None,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
) -> TurnOutcome:
    """The interview, once: keep what the learner said, then ask the next question or stop.

    The answer is recorded on the turn that asked it and nothing else happens to it: an interview
    answer is about the learner, not about a criterion, so it is never graded and no belief moves
    (that is T3's mapper's job, later, over the whole exchange). Then, in order (R3):

    * the compile has **failed** (``failure``): the session closes and says so, the answer kept;
    * the map has **landed** (``graph``): the interview ends here and the very same turn answers
      with the first lesson, so the learner never sees the seam;
    * otherwise the interviewer is asked for the next question, unless it has asked its share
      (``max_questions``) or says it has heard enough, in which case the session **warms**: an
      honest wait for the map, which ``advance_placement`` ends.

    An interviewer that cannot speak ends the interview rather than the turn: by now the answer is
    kept and the compile is running, and neither should be lost to a provider having a bad minute.
    """
    if session.status is SessionStatus.CLOSED:
        raise SessionClosedError(f"session {session.session_id} has already closed")
    if session.status is SessionStatus.WARMING:
        # A warming session's last turn asks nothing and every question before it is answered, so
        # an answer into it is an answer to a question that has been dealt with (P2a AD23): stale.
        raise StaleAnswerError(f"nothing is open on session {session.session_id}; it is warming")
    if session.status is not SessionStatus.PLACING:
        raise ValueError(f"session {session.session_id} is not placing")
    asked = session.turns[-1] if session.turns else None
    if asked is None or answering_seq != asked.seq or asked.answer is not None:
        raise StaleAnswerError(
            f"answer names turn {answering_seq}; nothing is open on session {session.session_id}"
        )

    turns = [*session.turns[:-1], asked.model_copy(update={"answer": answer})]
    exchanges = exchanges_of(turns)
    logger.info(
        "live.placement.answered",
        run_id=run_id,
        session_id=session.session_id,
        seq=asked.seq,
        exchanges=len(exchanges),
    )

    settled = await settle_placement(
        session,
        turns,
        mapper=mapper,
        graph=graph,
        failure=failure,
        model=model,
        tutor=tutor,
        run_id=run_id,
        elapsed_s=elapsed_s,
        budget_s=budget_s,
        on_delta=on_delta,
        sims=sims,
        prefetched=prefetched,
    )
    if settled is not None:
        return settled

    question = await _next_question(
        interviewer, session, exchanges, run_id=run_id, max_questions=max_questions
    )
    if question is None:
        return TurnOutcome(session=_warming(session, turns, run_id=run_id), model=model)
    following = SessionTurn(
        seq=len(turns) + 1,
        move=DirectorMove(kind=MoveKind.PLACE, reason=_ASKING_MORE),
        tutor=question,
        run_id=run_id,
    )
    return TurnOutcome(
        session=session.model_copy(update={"turns": [*turns, following]}), model=model
    )


#: Why the loop asks another question, in the words a trace reader gets.
_ASKING_MORE = "The map is still being built; one more thing about you first."


async def _next_question(
    interviewer: IInterviewer,
    session: Session,
    exchanges: list[InterviewExchange],
    *,
    run_id: str,
    max_questions: int,
) -> str | None:
    """The interviewer's next question, or ``None`` when the interview is over: because it has
    asked its share, because it has heard enough, or because it could not speak."""
    if len(exchanges) >= max_questions:
        logger.info(
            "live.placement.interview_bounded", run_id=run_id, session_id=session.session_id
        )
        return None
    try:
        return await interviewer.ask(session.topic or "", exchanges=exchanges, run_id=run_id)
    except InterviewerUnavailableError:
        logger.warning(
            "live.placement.interviewer_unavailable",
            run_id=run_id,
            session_id=session.session_id,
            exc_info=True,
        )
        return None


def _warming(session: Session, turns: list[SessionTurn], *, run_id: str) -> Session:
    logger.info("live.placement.warming", run_id=run_id, session_id=session.session_id)
    waiting = SessionTurn(
        seq=len(turns) + 1,
        move=DirectorMove(
            kind=MoveKind.PLACE, reason="The interview is over; the map is not here yet."
        ),
        tutor=_WARMING.format(topic=session.topic or "this"),
        run_id=run_id,
    )
    return session.model_copy(update={"turns": [*turns, waiting], "status": SessionStatus.WARMING})
