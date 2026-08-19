from collections.abc import Mapping

import structlog

from ..graph import ConceptGraph
from .exchanges_of import exchanges_of
from .next_turn import next_turn
from .opening_beliefs_of import opening_beliefs_of
from .prior_mapper_unavailable_error import PriorMapperUnavailableError
from .protocols import IPriorMapper, ISimRegistry, ITutor, ITutorDeltaSink
from .schema import (
    DirectorMove,
    LearnerModel,
    LessonParts,
    MoveKind,
    PlacementResult,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
)
from .seed_priors import seed_priors
from .turn_outcome import TurnOutcome

logger = structlog.get_logger()

#: How a session ends when its map never came. Names the topic and carries the compile's own
#: reason, made a sentence of its own: the learner is owed the same explanation the trace gets.
_MAP_FAILED = (
    "I couldn't build the map for {topic}, so we can't go on today. {reason} "
    "Start again with the same topic, or a different one."
)


async def settle_placement(
    session: Session,
    turns: list[SessionTurn],
    *,
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
) -> TurnOutcome | None:
    """What a placement does once its map's fate is known: teach from it, or close over its loss.

    Shared by the two ways a placement reaches that moment — the answer that arrives after the map
    landed (``take_placement_turn``) and the poll that finds it (``advance_placement``) — so the
    seam between placing and teaching is one seam and the goodbye over a lost map is one goodbye.
    ``None`` when the fate is not known yet (no map, no failure): the caller decides what to do
    with the wait.

    ``turns`` is the transcript as the caller has it, answer recorded; the settling turn is
    appended to it. Failure outranks a map, because a compile that failed after persisting a
    partial map is not a map to teach from.
    """
    if failure is not None:
        return TurnOutcome(
            session=_closed_over(session, turns, failure, run_id=run_id), model=model
        )
    if graph is None:
        return None
    placed = await _placed(mapper, session, turns, graph, run_id=run_id)
    model = seed_priors(model, placed.priors)
    # The delta's zero line (T5), stamped once the claims are on the model: a claim the learner
    # came in with is where they came in, not nothing.
    session = session.model_copy(update={"opening_beliefs": opening_beliefs_of(model)})
    if placed.profile:
        session = session.model_copy(update={"profile": placed.profile})
    taught, consumed = await _teaching_begins(
        session,
        graph,
        model,
        turns,
        tutor=tutor,
        run_id=run_id,
        elapsed_s=elapsed_s,
        budget_s=budget_s,
        on_delta=on_delta,
        sims=sims,
        prefetched=prefetched,
    )
    return TurnOutcome(session=taught, model=model, consumed_material=consumed)


async def _placed(
    mapper: IPriorMapper,
    session: Session,
    turns: list[SessionTurn],
    graph: ConceptGraph,
    *,
    run_id: str,
) -> PlacementResult:
    """What the interview came to (T3): the mapper's reading of it against the map, or nothing.

    Nothing rather than a failed turn when the mapper cannot place: a placement with no priors is
    a session taught from the root, which is what every session was before the interview existed,
    and the answers are still on the row for a later build to read again.
    """
    exchanges = exchanges_of(turns)
    if not exchanges:
        return PlacementResult()
    try:
        placed = await mapper.map(session.topic or graph.topic, exchanges, graph, run_id=run_id)
    except PriorMapperUnavailableError:
        logger.warning(
            "live.placement.mapper_unavailable",
            run_id=run_id,
            session_id=session.session_id,
            exc_info=True,
        )
        return PlacementResult()
    logger.info(
        "live.placement.placed",
        run_id=run_id,
        session_id=session.session_id,
        priors=len(placed.priors),
        profiled=bool(placed.profile),
    )
    return placed


async def _teaching_begins(
    session: Session,
    graph: ConceptGraph,
    model: LearnerModel,
    turns: list[SessionTurn],
    *,
    tutor: ITutor,
    run_id: str,
    elapsed_s: float,
    budget_s: float,
    on_delta: ITutorDeltaSink | None,
    sims: ISimRegistry | None,
    prefetched: Mapping[str, LessonParts] | None,
) -> tuple[Session, str | None]:
    """The interview is over and the map is here: the director's first move, said out loud. The
    clock is the session's own (the interview was inside its budget, A1) and the first lesson's
    turn number follows the last question's."""
    logger.info(
        "live.placement.teaching_begins",
        run_id=run_id,
        session_id=session.session_id,
        graph_id=graph.graph_id,
        exchanges=len(exchanges_of(turns)),
    )
    clock = SessionClock(turn=len(turns) + 1, elapsed_s=elapsed_s, budget_s=budget_s)
    return await next_turn(
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


def _closed_over(
    session: Session, turns: list[SessionTurn], reason: str, *, run_id: str
) -> Session:
    """End a placement whose compile failed, out loud (P2a AD22: the transcript is what the learner
    reads, and a session that stopped talking is indistinguishable from one that crashed). Written
    deterministically: there is no tutor to ask, because there is no map to teach from."""
    logger.warning(
        "live.placement.map_failed", run_id=run_id, session_id=session.session_id, reason=reason
    )
    move = DirectorMove(kind=MoveKind.CLOSE, reason=f"The map could not be built: {reason}"[:500])
    goodbye = SessionTurn(
        seq=len(turns) + 1,
        move=move,
        tutor=_MAP_FAILED.format(topic=session.topic or "this", reason=_sentence(reason)),
        run_id=run_id,
    )
    return session.model_copy(update={"turns": [*turns, goodbye], "status": SessionStatus.CLOSED})


def _sentence(reason: str) -> str:
    """The compile's reason as a sentence a learner can read: capitalised, ending in a full stop.
    The compiler's own messages are lowercase log-style fragments ("could not decompose 'X' into
    concepts"); dropped verbatim between two sentences they read as a run-on (found in review)."""
    text = reason.strip().rstrip(".") or "The compile failed"
    return text[0].upper() + text[1:] + "."
