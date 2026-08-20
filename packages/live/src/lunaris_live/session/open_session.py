from collections.abc import Mapping
from datetime import UTC, datetime

from ..graph import ConceptGraph
from .decide_move import decide_move
from .earliest_due import earliest_due
from .next_turn import next_turn
from .nothing_to_teach_error import NothingToTeachError
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

    Raises ``NothingToTeachError`` (a ``ValueError``) when the map has nothing to teach: an empty
    graph, one whose teaching order names concepts it does not contain, or a finished map whose
    reviews are not yet due (T6) leaves the director with nothing to do and its first move is to
    close. Handing a learner a session that opens on "we're done" is worse than telling the caller
    so — and telling them the day the next review is due, when there is one.

    Raises ``TutorUnavailableError`` when the tutor cannot speak — the turn did not happen, so
    neither did the session.
    """
    # Stamped once, here, at the only moment a session is born: the wall time the caller opened it
    # at (a session opened "on Thursday" starts on Thursday, T6), else now. Every later read
    # carries it, and every later turn's wall time is derived from it.
    started_at = clock.at or datetime.now(UTC)
    clock = clock.model_copy(update={"at": started_at})
    if decide_move(graph, model, clock).kind is MoveKind.CLOSE:
        raise NothingToTeachError(
            graph.graph_id,
            next_review_at=earliest_due(known.due_at for known in model.nodes.values()),
        )
    shell = Session(
        session_id=session_id,
        graph_id=graph.graph_id,
        # The map's own topic, which is what the schema has always said a map-opened session
        # carries and what a list of sessions is recognised by (T2). A session named only by its
        # ids is a row a learner cannot pick their own work out of.
        topic=graph.topic,
        started_at=started_at,
        # And what the learner came in holding (P2c T5): the mastery delta's zero line.
        opening_beliefs=opening_beliefs_of(model),
    )
    return await next_turn(
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
