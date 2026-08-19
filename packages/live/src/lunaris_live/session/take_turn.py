import structlog

from ..graph import ConceptGraph, ConceptNode
from .apply_evidence import apply_evidence
from .compose_layout import compose_layout
from .decide_move import decide_move
from .grader_unavailable_error import GraderUnavailableError
from .max_answer_chars import MAX_ANSWER_CHARS
from .placement_not_answerable_error import PlacementNotAnswerableError
from .protocols import IGrader, ISimRegistry, ITutor, ITutorDeltaSink
from .resolve_sim_app import resolve_sim_app
from .said_and_illustrated import said_and_illustrated
from .schema import (
    DirectorMove,
    LayoutSpec,
    LearnerModel,
    LessonParts,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
    SurfaceSpec,
    TurnGrade,
)
from .select_surface import select_surface
from .session_closed_error import SessionClosedError
from .stage_criterion import stage_criterion
from .stale_answer_error import StaleAnswerError
from .turn_outcome import TurnOutcome

logger = structlog.get_logger()

#: How a session signs off. Deliberately plain and deliberately not generated: a goodbye is the one
#: turn with nothing to teach, and P2c replaces it with the real ceremony (recap, mastery delta,
#: what to come back to) rather than with better prose.
_CLOSING = "That's where we'll stop for today."


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
    if session.status is SessionStatus.PLACING:
        # T1's honest refusal; T2 routes this to the interviewer instead and deletes it.
        raise PlacementNotAnswerableError(f"session {session.session_id} is still placing")
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
    move = decide_move(graph, model, clock)
    if move.kind is MoveKind.CLOSE:
        # The surface is chosen from the same three inputs the move was (T3), so a close shows what
        # the learner demonstrated rather than an empty card.
        closing = select_surface(move, None, graph=graph, criterion=None, model=model, clock=clock)
        return TurnOutcome(
            session=_closed(
                session,
                turns,
                move,
                run_id=run_id,
                surface=closing,
                # A goodbye names no concept and asked no tutor for material, so the lean layout is
                # all there is to arrange: the sign-off and the meter. Composed rather than left
                # ``None`` so that "every turn has a layout" is true of the last one too, and a
                # renderer never has to hold a second way of drawing a turn.
                layout=compose_layout(LessonParts(), node_id=None, model=model),
            ),
            model=model,
        )

    taught = await _teach(
        graph,
        move,
        turns,
        tutor=tutor,
        run_id=run_id,
        on_delta=on_delta,
        model=model,
        clock=clock,
        sims=sims,
    )
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
    session: Session,
    turns: list[SessionTurn],
    move: DirectorMove,
    *,
    run_id: str,
    surface: SurfaceSpec,
    layout: LayoutSpec,
) -> Session:
    """The session, ended — and said out loud.

    The goodbye is a turn rather than only a status, because ``status`` is a field and the
    transcript is what the learner reads: a session that ended by going quiet is indistinguishable
    from one that crashed. It is written deterministically rather than by the tutor, which teaches
    concepts and is deliberately refused a CLOSE — a close is about the session, not a concept.

    The recap, the mastery delta and the spaced-retrieval schedule are P2c's ceremony. What is owed
    here is that a session which has run out of material or out of time stops rather than looping,
    ends visibly, and says why.
    """
    logger.info(
        "live.session.closed",
        run_id=run_id,
        session_id=session.session_id,
        reason=move.reason,
        turn_count=len(turns),
    )
    goodbye = SessionTurn(
        seq=len(turns) + 1,
        move=move,
        # The director's own reason, verbatim: the learner is owed the same explanation the trace
        # gets, and two wordings of one decision is how the two come to disagree.
        tutor=f"{_CLOSING} {move.reason}",
        run_id=run_id,
        surface=surface,
        layout=layout,
    )
    return session.model_copy(update={"turns": [*turns, goodbye], "status": SessionStatus.CLOSED})


async def _teach(
    graph: ConceptGraph,
    move: DirectorMove,
    turns: list[SessionTurn],
    *,
    tutor: ITutor,
    run_id: str,
    on_delta: ITutorDeltaSink | None,
    model: LearnerModel,
    clock: SessionClock,
    sims: ISimRegistry | None,
) -> SessionTurn:
    """The next turn: the move, said out loud, with something staged for the learner to meet."""
    node = _node_of(graph, move.node_id) if move.node_id is not None else None
    if node is None:
        # Unreachable from ``decide_move``, which only ever names a concept it read off this graph.
        # Kept because it is the one assumption a turn makes about its collaborator, and a broken
        # one would otherwise surface as an AttributeError from inside the tutor.
        raise ValueError(f"{move.node_id} is not a concept on graph {graph.graph_id}")

    staged = stage_criterion(node, sims=sims)
    app = resolve_sim_app(sims, node, staged)
    # Only this concept's history: a tutor told everything it has ever said would spend the prompt
    # on material the learner is not being taught right now.
    already_said = [turn.tutor for turn in turns if turn.move.node_id == node.id]

    said, parts = await said_and_illustrated(
        tutor,
        move,
        node,
        topic=graph.topic,
        criterion=staged,
        already_said=already_said,
        run_id=run_id,
        on_delta=on_delta,
    )
    return SessionTurn(
        seq=len(turns) + 1,
        move=move,
        tutor=said,
        run_id=run_id,
        criterion=staged,
        # Chosen from the move, the concept and the belief — never from what the tutor happened to
        # say. Plan §8 makes that mandatory for this tier: these components feed the learner model.
        surface=select_surface(
            move, node, graph=graph, criterion=staged, model=model, clock=clock, sim=app
        ),
        # Tier 2 (T5): the tutor wrote the material, the rules decide what this learner sees of it.
        layout=compose_layout(parts, node_id=node.id, model=model),
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
