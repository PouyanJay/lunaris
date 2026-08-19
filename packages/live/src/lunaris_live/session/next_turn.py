from collections.abc import Mapping

import structlog

from ..graph import ConceptGraph
from .compose_layout import compose_layout
from .covered_in import covered_in
from .decide_move import decide_move
from .node_of import node_of
from .protocols import ISimRegistry, ITutor, ITutorDeltaSink
from .recap_sentence import recap_sentence
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
from .tutor_unavailable_error import TutorUnavailableError

logger = structlog.get_logger()


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
    prefetched: Mapping[str, LessonParts] | None = None,
) -> tuple[Session, str | None]:
    """What happens next on this map, said out loud: the director decides, and the turn is taken.

    The half of the loop that comes *after* an answer has been dealt with, shared by the two places
    a session moves on from (P2c): an answered lesson (``take_turn``) and an interview that has
    ended with the map in hand (``take_placement_turn`` / ``advance_placement``). One function so
    that the seam between placement and teaching cannot be a second, slightly different way of
    deciding and teaching a turn.

    ``turns`` is the transcript as it stands after the answer was recorded; the new turn is
    appended to it. A ``CLOSE`` move ends the session and says why; anything else teaches, and the
    session is ``ACTIVE`` from then on (a placing session becomes an active one here).

    ``prefetched`` is first-turn material by concept, read from the store by the caller (P2c T4).
    A first turn on a concept whose material is there uses it and asks the tutor for words only;
    the second value returned names that concept, so the caller can let the store go of it. A later
    turn on a concept never reads it: a remediation generates fresh.
    """
    move = decide_move(graph, model, clock)
    if move.kind is MoveKind.CLOSE:
        return await _close(
            session, graph, model, turns, move, clock=clock, tutor=tutor, run_id=run_id
        ), None

    taught, consumed = await _teach(
        graph,
        move,
        turns,
        tutor=tutor,
        run_id=run_id,
        on_delta=on_delta,
        model=model,
        clock=clock,
        sims=sims,
        profile=session.profile,
        prefetched=prefetched or {},
    )
    logger.info(
        "live.session.turn_taken",
        run_id=run_id,
        session_id=session.session_id,
        seq=taught.seq,
        move=move.kind.value,
        node=move.node_id,
    )
    return (
        session.model_copy(update={"turns": [*turns, taught], "status": SessionStatus.ACTIVE}),
        consumed,
    )


async def _close(
    session: Session,
    graph: ConceptGraph,
    model: LearnerModel,
    turns: list[SessionTurn],
    move: DirectorMove,
    *,
    clock: SessionClock,
    tutor: ITutor,
    run_id: str,
) -> Session:
    """The session, ended with its ceremony (P2c T5): the meter of what was demonstrated beside
    where each concept stood at open (the delta), the recap over what was covered, and the
    director's reason. The surface is chosen from the same inputs the move was (T3), so a close
    shows what the learner did rather than an empty card."""
    closing = select_surface(
        move,
        None,
        graph=graph,
        criterion=None,
        model=model,
        clock=clock,
        opening_beliefs=session.opening_beliefs,
    )
    return _closed(
        session,
        turns,
        move,
        run_id=run_id,
        recap=await _recap(tutor, session, graph, model, turns, run_id=run_id),
        surface=closing,
        # A goodbye names no concept and asked no tutor for material, so the lean layout is all
        # there is to arrange: the sign-off and the meter. Composed rather than left ``None`` so
        # that "every turn has a layout" is true of the last one too, and a renderer never has to
        # hold a second way of drawing a turn.
        layout=compose_layout(LessonParts(), node_id=None, model=model),
    )


async def _recap(
    tutor: ITutor,
    session: Session,
    graph: ConceptGraph,
    model: LearnerModel,
    turns: list[SessionTurn],
    *,
    run_id: str,
) -> str:
    """The recap in the tutor's words, or the plain sentence when it cannot speak (P2c T5).

    Briefed with the record (``covered_in``), which the tutor may dress and never revise. A tutor
    that cannot write it does not fail the close: the ceremony is owed and the words are a nicety,
    so the plain recap stands in and the failure is a warning worth seeing, not a session that
    ended in an error.
    """
    covered = covered_in(turns, graph, model)
    try:
        return await tutor.recap(graph.topic, covered, profile=session.profile, run_id=run_id)
    except TutorUnavailableError:
        logger.warning(
            "live.session.recap_unavailable",
            run_id=run_id,
            session_id=session.session_id,
            exc_info=True,
        )
        return recap_sentence(graph.topic, covered)


def _closed(
    session: Session,
    turns: list[SessionTurn],
    move: DirectorMove,
    *,
    run_id: str,
    recap: str,
    surface: SurfaceSpec,
    layout: LayoutSpec,
) -> Session:
    """The session, ended — and said out loud.

    The goodbye is a turn rather than only a status, because ``status`` is a field and the
    transcript is what the learner reads: a session that ended by going quiet is indistinguishable
    from one that crashed. ``recap`` is the tutor's over the record, or the plain sentence (P2c
    T5); the director's own reason still closes it, verbatim, because the learner is owed the
    same explanation the trace gets and two wordings of one decision is how the two come to
    disagree.

    The spaced-retrieval schedule is T6's part of the ceremony. What is owed here is that a session
    which has run out of material or out of time stops rather than looping, ends visibly, says what
    it covered, and says why it stopped.
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
        tutor=f"{recap.strip()} {move.reason}",
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
    profile: str | None = None,
    prefetched: Mapping[str, LessonParts],
) -> tuple[SessionTurn, str | None]:
    """The next turn: the move, said out loud, with something staged for the learner to meet, and
    the concept whose prefetched material it used (or ``None``)."""
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
    # First-turn material only (P2c T4): a second pass over a concept generates fresh, because
    # coming at a stuck concept a different way each time is what the P2a eval showed works.
    material = prefetched.get(node.id) if not already_said else None

    said, parts = await said_and_illustrated(
        tutor,
        move,
        node,
        topic=graph.topic,
        criterion=staged,
        already_said=already_said,
        profile=profile,
        run_id=run_id,
        on_delta=on_delta,
        prefetched=material,
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
    ), (node.id if material is not None else None)
