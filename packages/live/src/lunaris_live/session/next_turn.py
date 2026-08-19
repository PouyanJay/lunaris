import structlog

from ..graph import ConceptGraph
from .compose_layout import compose_layout
from .decide_move import decide_move
from .node_of import node_of
from .protocols import ISimRegistry, ITutor, ITutorDeltaSink
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
)
from .select_surface import select_surface
from .stage_criterion import stage_criterion

logger = structlog.get_logger()

#: How a session signs off. Deliberately plain and deliberately not generated: a goodbye is the one
#: turn with nothing to teach, and P2c replaces it with the real ceremony (recap, mastery delta,
#: what to come back to) rather than with better prose.
_CLOSING = "That's where we'll stop for today."


async def next_turn(
    session: Session,
    graph: ConceptGraph,
    model: LearnerModel,
    turns: list[SessionTurn],
    *,
    clock: SessionClock,
    tutor: ITutor,
    run_id: str,
    on_delta: ITutorDeltaSink | None = None,
    sims: ISimRegistry | None = None,
) -> Session:
    """What happens next on this map, said out loud: the director decides, and the turn is taken.

    The half of the loop that comes *after* an answer has been dealt with, shared by the two places
    a session moves on from (P2c): an answered lesson (``take_turn``) and an interview that has
    ended with the map in hand (``take_placement_turn`` / ``advance_placement``). One function so
    that the seam between placement and teaching cannot be a second, slightly different way of
    deciding and teaching a turn.

    ``turns`` is the transcript as it stands after the answer was recorded; the new turn is
    appended to it. A ``CLOSE`` move ends the session and says why; anything else teaches, and the
    session is ``ACTIVE`` from then on (a placing session becomes an active one here).
    """
    move = decide_move(graph, model, clock)
    if move.kind is MoveKind.CLOSE:
        # The surface is chosen from the same three inputs the move was (T3), so a close shows what
        # the learner demonstrated rather than an empty card.
        closing = select_surface(move, None, graph=graph, criterion=None, model=model, clock=clock)
        return _closed(
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
    )
    return session.model_copy(update={"turns": [*turns, taught], "status": SessionStatus.ACTIVE})


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
    node = node_of(graph, move.node_id) if move.node_id is not None else None
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
