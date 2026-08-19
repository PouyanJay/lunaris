from collections.abc import Mapping

import structlog

from ..graph import ConceptGraph
from .apply_evidence import apply_evidence
from .grader_unavailable_error import GraderUnavailableError
from .max_answer_chars import MAX_ANSWER_CHARS
from .next_turn import next_turn
from .node_of import node_of
from .protocols import IGrader, ISimRegistry, ITutor, ITutorDeltaSink
from .schema import (
    LearnerModel,
    LessonParts,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
    TurnGrade,
)
from .session_closed_error import SessionClosedError
from .stale_answer_error import StaleAnswerError
from .turn_outcome import TurnOutcome

logger = structlog.get_logger()


async def take_turn(
    session: Session,
    graph: ConceptGraph,
    model: LearnerModel,
    *,
    answer: str,
    answering_seq: int,
    grader: IGrader,
    tutor: ITutor,
    run_id: str,
    elapsed_s: float,
    budget_s: float,
    on_delta: ITutorDeltaSink | None = None,
    sims: ISimRegistry | None = None,
    prefetched: Mapping[str, LessonParts] | None = None,
) -> TurnOutcome:
    """The loop, once: score what the learner just said, move the belief, decide what happens next.

    The order is the point. The answer is graded against the criterion the *last* turn staged, the
    belief that produces is written before anything is decided, and only then does the director
    read the model — so a turn's move is a response to what the learner actually demonstrated
    rather than to what they demonstrated one turn ago.

    An ungraded answer is a real outcome and not a failure: a concept whose criteria all need a
    simulator (Phase 3) stages nothing, so there is nothing to score. The answer is still recorded
    and the session still advances, because stranding somebody on a concept the map cannot yet
    check would be the map's problem made into the learner's.

    ``answering_seq`` is the turn the learner was looking at when they answered. It is named rather
    than assumed, because a duplicate submit would otherwise be graded against the question that
    replaced it — recorded under a criterion it was never written for.

    ``on_delta`` is where the tutor's words go *while* they are being written (P2b A2). Passing one
    switches the tutor to its streaming path; leaving it ``None`` is P2a's turn exactly, single call
    and all, which is what the REST endpoint keeps. It is deliberately not the loop's business
    whether anybody is listening: a failing sink costs a fragment and never the turn.

    Raises ``StaleAnswerError`` when the named turn is not the one in front of the learner,
    ``SessionClosedError`` on a session the director has already ended, and
    ``GraderUnavailableError`` / ``TutorUnavailableError`` when a turn could not be taken at all —
    in which case nothing has moved and the caller can offer the learner a retry that means
    something.
    """
    if session.status is not SessionStatus.ACTIVE:
        raise SessionClosedError(f"session {session.session_id} has already closed")
    if not session.turns:
        raise ValueError(f"session {session.session_id} has no turn to answer")

    asked = session.turns[-1]
    if answering_seq != asked.seq:
        raise StaleAnswerError(
            f"answer names turn {answering_seq}; {session.session_id} is on turn {asked.seq}"
        )

    said = answer.strip()[:MAX_ANSWER_CHARS]
    graded = await _grade(asked, graph, said=said, grader=grader, run_id=run_id)

    # Written before the director looks: a move decided against the pre-answer belief would be one
    # turn behind the learner, which is exactly the lag adaptive teaching exists to remove.
    model = _moved_by(model, asked, graded)
    turns = [*session.turns[:-1], asked.model_copy(update={"answer": said, "grade": graded})]

    clock = SessionClock(turn=len(turns) + 1, elapsed_s=elapsed_s, budget_s=budget_s)
    advanced, consumed = await next_turn(
        session,
        graph,
        model,
        turns,
        clock=clock,
        tutor=tutor,
        run_id=run_id,
        on_delta=on_delta,
        sims=sims,
        prefetched=prefetched,
    )
    logger.info(
        "live.session.turn_graded",
        run_id=run_id,
        session_id=session.session_id,
        seq=asked.seq,
        # The verdict, never the answer: an operational log is not the place for a transcript of
        # somebody being taught, and this is enough to read a session's shape from the outside.
        graded=graded.kind.value if graded else None,
    )
    return TurnOutcome(session=advanced, model=model, consumed_material=consumed)


def _moved_by(model: LearnerModel, asked: SessionTurn, graded: TurnGrade | None) -> LearnerModel:
    """The belief after this answer — unchanged when there was nothing to score it against."""
    if graded is None or asked.move.node_id is None:
        return model
    return apply_evidence(model, asked.move.node_id, graded.kind, at_turn=asked.seq)


async def _grade(
    asked: SessionTurn, graph: ConceptGraph, *, said: str, grader: IGrader, run_id: str
) -> TurnGrade | None:
    """The verdict on ``said``, or ``None`` when the turn staged nothing to be scored on.

    A grader that cannot answer is *not* a wrong answer — ``GraderUnavailableError`` is left to
    propagate rather than folded into NOT_MET, because a bad minute for the provider must never
    teach the system that a learner does not understand a concept.
    """
    if asked.criterion is None or asked.move.node_id is None:
        return None
    node = node_of(graph, asked.move.node_id)
    if node is None:
        # The map moved under the session (C1 can rewrite what a node is called, and a graph can be
        # re-read between turns). Refusing to invent a subject for the grading is the honest end.
        logger.warning(
            "live.grader.node_gone", run_id=run_id, node=asked.move.node_id, seq=asked.seq
        )
        raise GraderUnavailableError(f"{asked.move.node_id} is no longer on the map")
    return await grader.grade(said, criterion=asked.criterion, node=node, run_id=run_id)
