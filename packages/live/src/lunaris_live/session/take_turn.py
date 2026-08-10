import structlog

from ..graph import ConceptGraph, ConceptNode
from .apply_evidence import apply_evidence
from .decide_move import decide_move
from .grader_unavailable_error import GraderUnavailableError
from .max_answer_chars import MAX_ANSWER_CHARS
from .protocols import IGrader, ITutor
from .schema import (
    DirectorMove,
    LearnerModel,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
    TurnGrade,
)
from .session_closed_error import SessionClosedError
from .stage_criterion import stage_criterion
from .turn_outcome import TurnOutcome

logger = structlog.get_logger()


async def take_turn(
    session: Session,
    graph: ConceptGraph,
    model: LearnerModel,
    *,
    answer: str,
    grader: IGrader,
    tutor: ITutor,
    run_id: str,
    budget_s: float,
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

    Raises ``SessionClosedError`` on a session the director has already ended, and
    ``GraderUnavailableError`` / ``TutorUnavailableError`` when a turn could not be taken at all —
    in which case nothing has moved and the caller can offer the learner a retry that means
    something.
    """
    if session.status is not SessionStatus.ACTIVE:
        raise SessionClosedError(f"session {session.session_id} has already closed")
    if not session.turns:
        raise ValueError(f"session {session.session_id} has no turn to answer")

    asked = session.turns[-1]
    said = answer.strip()[:MAX_ANSWER_CHARS]
    graded = await _grade(asked, graph, said=said, grader=grader, run_id=run_id)

    # Written before the director looks: a move decided against the pre-answer belief would be one
    # turn behind the learner, which is exactly the lag adaptive teaching exists to remove.
    model = _moved_by(model, asked, graded)
    turns = [*session.turns[:-1], asked.model_copy(update={"answer": said, "grade": graded})]

    clock = SessionClock(turn=len(turns) + 1, elapsed_s=0.0, budget_s=budget_s)
    move = decide_move(graph, model, clock)
    if move.kind is MoveKind.CLOSE:
        return TurnOutcome(session=_closed(session, turns, move, run_id=run_id), model=model)

    taught = await _teach(graph, move, turns, tutor=tutor, run_id=run_id)
    logger.info(
        "live.session.turn_taken",
        run_id=run_id,
        session_id=session.session_id,
        seq=taught.seq,
        move=move.kind.value,
        node=move.node_id,
        # The verdict, never the answer: an operational log is not the place for a transcript of
        # somebody being taught, and this is enough to read a session's shape from the outside.
        graded=graded.kind.value if graded else None,
    )
    return TurnOutcome(session=session.model_copy(update={"turns": [*turns, taught]}), model=model)


def _moved_by(model: LearnerModel, asked: SessionTurn, graded: TurnGrade | None) -> LearnerModel:
    """The belief after this answer — unchanged when there was nothing to score it against."""
    if graded is None or asked.move.node_id is None:
        return model
    return apply_evidence(model, asked.move.node_id, graded.kind, at_turn=asked.seq)


def _closed(
    session: Session, turns: list[SessionTurn], move: DirectorMove, *, run_id: str
) -> Session:
    """The session, ended. The closing words are P2c's ceremony; what T5 owes is that a session
    which has run out of material stops rather than looping, and that the last thing left in the
    transcript is still the turn the learner answered."""
    logger.info(
        "live.session.closed",
        run_id=run_id,
        session_id=session.session_id,
        reason=move.reason,
        turn_count=len(turns),
    )
    return session.model_copy(update={"turns": turns, "status": SessionStatus.CLOSED})


async def _teach(
    graph: ConceptGraph,
    move: DirectorMove,
    turns: list[SessionTurn],
    *,
    tutor: ITutor,
    run_id: str,
) -> SessionTurn:
    """The next turn: the move, said out loud, with something staged for the learner to meet."""
    node = _node_of(graph, move.node_id) if move.node_id is not None else None
    if node is None:
        # Unreachable from ``decide_move``, which only ever names a concept it read off this graph.
        # Kept because it is the one assumption a turn makes about its collaborator, and a broken
        # one would otherwise surface as an AttributeError from inside the tutor.
        raise ValueError(f"{move.node_id} is not a concept on graph {graph.graph_id}")

    staged = stage_criterion(node)
    return SessionTurn(
        seq=len(turns) + 1,
        move=move,
        tutor=await tutor.teach(
            move,
            node,
            topic=graph.topic,
            criterion=staged,
            # Only this concept's history: a tutor told everything it has ever said would spend the
            # prompt on material the learner is not being taught right now.
            already_said=[turn.tutor for turn in turns if turn.move.node_id == node.id],
            run_id=run_id,
        ),
        run_id=run_id,
        criterion=staged,
    )


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
    node = _node_of(graph, asked.move.node_id)
    if node is None:
        # The map moved under the session (C1 can rewrite what a node is called, and a graph can be
        # re-read between turns). Refusing to invent a subject for the grading is the honest end.
        logger.warning(
            "live.grader.node_gone", run_id=run_id, node=asked.move.node_id, seq=asked.seq
        )
        raise GraderUnavailableError(f"{asked.move.node_id} is no longer on the map")
    return await grader.grade(said, criterion=asked.criterion, node=node, run_id=run_id)


def _node_of(graph: ConceptGraph, node_id: str) -> ConceptNode | None:
    return next((node for node in graph.nodes if node.id == node_id), None)
