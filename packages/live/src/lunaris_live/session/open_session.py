from collections.abc import Mapping
from datetime import UTC, datetime

from ..graph import ConceptGraph
from .decide_move import decide_move
from .next_turn import next_turn
from .opening_beliefs_of import opening_beliefs_of
from .protocols import ISimRegistry, ITutor
from .schema import LearnerModel, LessonParts, MoveKind, Session, SessionClock
from .turn_outcome import TurnOutcome


async def open_session(
    graph: ConceptGraph,
    model: LearnerModel,
    clock: SessionClock,
    *,
    session_id: str,
    run_id: str,
    tutor: ITutor,
    sims: ISimRegistry | None = None,
    prefetched: Mapping[str, LessonParts] | None = None,
) -> TurnOutcome:
    """Open a session on ``graph`` and take its first turn.

    Both halves of the turn are real here: the director picks the move from what this learner is
    believed to know (T2, T3), and the tutor says it (T4). The learner model is why a returning
    learner does not start over at the root — a session that always opened on ``topo_order[0]``
    would be correctly wired and would re-teach somebody the thing they came back having learned.

    The first turn is ``next_turn`` on an empty session (P2c T4): the same deciding, the same
    teaching, the same reading of kept material as every turn after it, so an opening cannot be a
    second, slightly different way of taking a turn — and what it consumed is on the outcome, for
    the caller to let the store go of.

    Raises ``ValueError`` when the map has nothing to teach: an empty graph, or one whose teaching
    order names concepts it does not contain, leaves the director with nothing to introduce and its
    first move is to close. Handing a learner a session that opens on "we're done" is worse than
    telling the caller the map is broken.

    Raises ``TutorUnavailableError`` when the tutor cannot speak — the turn did not happen, so
    neither did the session.
    """
    if decide_move(graph, model, clock).kind is MoveKind.CLOSE:
        raise ValueError(f"graph {graph.graph_id} has nothing to teach")
    shell = Session(
        session_id=session_id,
        graph_id=graph.graph_id,
        # Stamped once, here, at the only moment a session is born. Every later read carries it.
        started_at=datetime.now(UTC),
        # And what the learner came in holding (P2c T5): the mastery delta's zero line.
        opening_beliefs=opening_beliefs_of(model),
    )
    session, consumed = await next_turn(
        shell,
        graph,
        model,
        [],
        clock=clock,
        tutor=tutor,
        run_id=run_id,
        sims=sims,
        prefetched=prefetched,
    )
    return TurnOutcome(session=session, model=model, consumed_material=consumed)
