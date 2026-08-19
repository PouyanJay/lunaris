from ..graph import ConceptGraph, ConceptNode


def node_of(graph: ConceptGraph, node_id: str) -> ConceptNode | None:
    """The concept ``node_id`` names on ``graph``, or ``None`` when the map no longer has it (C1
    can rewrite a map between turns; a session that read a stale id has to be able to say so)."""
    return next((node for node in graph.nodes if node.id == node_id), None)
