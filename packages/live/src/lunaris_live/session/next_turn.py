from collections.abc import Mapping

import structlog

from ..graph import ConceptGraph
from .close_session import close_session
from .compose_layout import compose_layout
from .decide_move import decide_move
from .node_of import node_of
from .on_the_wall import on_the_wall
from .protocols import ISimRegistry, ITutor, ITutorDeltaSink
from .resolve_sim_app import resolve_sim_app
from .said_and_illustrated import said_and_illustrated
from .schema import (
    DirectorMove,
    LearnerModel,
    LessonParts,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
)
from .select_surface import select_surface
from .stage_criterion import stage_criterion
from .turn_outcome import TurnOutcome

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
) -> TurnOutcome:
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
    the outcome names that concept, so the caller can let the store go of it. A later turn on a
    concept never reads it: a remediation generates fresh.

    Returns the whole outcome — session, model, consumed material — because a close moves the
    model too (T6: the schedule is written at close), and a caller handed the session alone would
    persist a learner whose transcript says "come back Thursday" and whose beliefs say nothing.
    """
    clock = on_the_wall(clock, session)
    move = decide_move(graph, model, clock)
    if move.kind is MoveKind.CLOSE:
        return await close_session(
            session, graph, model, turns, move, clock=clock, tutor=tutor, run_id=run_id
        )

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
    return TurnOutcome(
        session=session.model_copy(
            update={"turns": [*turns, taught], "status": SessionStatus.ACTIVE}
        ),
        model=model,
        consumed_material=consumed,
    )


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
