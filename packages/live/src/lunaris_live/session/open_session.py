from ..graph import ConceptGraph
from .schema import DirectorMove, MoveKind, Session, SessionTurn

#: The walking skeleton's stand-in for the tutor (T4 replaces it with a real one). Deliberately
#: names the concept rather than being lorem: a fixed string that mentioned nothing would let the
#: whole path be wired to the wrong node without any test noticing.
_OPENING = "Let's start with {name}. {definition}"


def open_session(graph: ConceptGraph, *, session_id: str) -> Session:
    """Open a session on ``graph`` and take its first turn.

    The skeleton's move policy is "the first concept in the map's own teaching order", which is not
    the director (T3) — but it is not arbitrary either: ``topo_order`` puts prerequisites first, so
    the opening concept provably has nothing before it. A skeleton that opened in the middle of the
    map would be wired correctly and pedagogically wrong, and the difference matters enough that the
    test pins it now rather than after the director lands.

    Raises ``ValueError`` on a map with no concepts — there is nothing to teach, and a session that
    opened on it would show the learner an empty transcript and call it a lesson.
    """
    if not graph.topo_order:
        raise ValueError(f"graph {graph.graph_id} has no concepts to teach")

    first = next(node for node in graph.nodes if node.id == graph.topo_order[0])
    move = DirectorMove(
        kind=MoveKind.INTRODUCE,
        node_id=first.id,
        reason="Opening concept: it is first in the map's teaching order, so nothing precedes it.",
    )
    return Session(
        session_id=session_id,
        graph_id=graph.graph_id,
        turns=[
            SessionTurn(
                seq=1,
                move=move,
                tutor=_OPENING.format(name=first.name, definition=first.definition),
            )
        ],
    )
