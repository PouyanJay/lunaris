from collections.abc import Mapping

from ..graph import ConceptGraph
from .protocols import IPriorMapper, ISimRegistry, ITutor, ITutorDeltaSink
from .schema import LearnerModel, LessonParts, Session, SessionStatus
from .settle_placement import settle_placement
from .turn_outcome import TurnOutcome


async def advance_placement(
    session: Session,
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
    """Move a warming session on, if there is anywhere for it to go yet (P2c).

    ``None`` means "still warming, nothing to do": a distinct answer rather than an unchanged
    session, so a caller can say so (202) without diffing rows. With the map, teaching begins;
    with a failure, the session closes and says so. Anything but a warming session is a caller
    error: a placing session moves on through its answers, an active one through the loop.
    """
    if session.status is not SessionStatus.WARMING:
        raise ValueError(f"session {session.session_id} is not warming")
    return await settle_placement(
        session,
        list(session.turns),
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
