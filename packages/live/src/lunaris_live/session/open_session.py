from datetime import UTC, datetime

from ..graph import ConceptGraph
from .compose_layout import compose_layout
from .decide_move import decide_move
from .protocols import ITutor
from .said_and_illustrated import said_and_illustrated
from .schema import LearnerModel, Session, SessionClock, SessionTurn
from .select_surface import select_surface
from .stage_criterion import stage_criterion


async def open_session(
    graph: ConceptGraph,
    model: LearnerModel,
    clock: SessionClock,
    *,
    session_id: str,
    run_id: str,
    tutor: ITutor,
) -> Session:
    """Open a session on ``graph`` and take its first turn.

    Both halves of the turn are real here: the director picks the move from what this learner is
    believed to know (T2, T3), and the tutor says it (T4). The learner model is why a returning
    learner does not start over at the root — a session that always opened on ``topo_order[0]``
    would be correctly wired and would re-teach somebody the thing they came back having learned.

    Raises ``ValueError`` when the map has nothing to teach: an empty graph, or one whose teaching
    order names concepts it does not contain, leaves the director with nothing to introduce and its
    first move is to close. Handing a learner a session that opens on "we're done" is worse than
    telling the caller the map is broken.

    Raises ``TutorUnavailableError`` when the tutor cannot speak — the turn did not happen, so
    neither did the session.
    """
    move = decide_move(graph, model, clock)
    node = next((n for n in graph.nodes if n.id == move.node_id), None)
    if node is None:
        raise ValueError(f"graph {graph.graph_id} has nothing to teach")

    # Staged now rather than when the answer arrives: the tutor has to ask for it in its own words
    # as part of the teaching, and the turn has to record what was asked (U1).
    staged = stage_criterion(node)
    said, parts = await said_and_illustrated(
        tutor,
        move,
        node,
        topic=graph.topic,
        criterion=staged,
        already_said=(),
        run_id=run_id,
    )
    return Session(
        session_id=session_id,
        graph_id=graph.graph_id,
        # Stamped once, here, at the only moment a session is born. Every later read carries it.
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn(
                seq=clock.turn,
                move=move,
                tutor=said,
                run_id=run_id,
                criterion=staged,
                surface=select_surface(
                    move, node, graph=graph, criterion=staged, model=model, clock=clock
                ),
                layout=compose_layout(parts, node_id=node.id, model=model),
            )
        ],
    )
