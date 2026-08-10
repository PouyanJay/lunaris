from .schema import ConceptGraph


def prerequisites_of(graph: ConceptGraph, node_id: str) -> list[str]:
    """Everything ``node_id`` needs first, in the order the graph teaches them.

    The whole chain, not just the direct claims: a learner missing the root is missing everything
    above it, and answering with one layer would have the director check a prerequisite whose own
    prerequisite is absent.

    Ordered by the graph's own ``topo_order`` so two answers about one graph cannot disagree about
    sequence. An unknown concept has no prerequisites rather than being an error — the director asks
    this about whatever the learner just said, which is not always something the map has.
    """
    requires = {node.id: node.requires for node in graph.nodes}
    if node_id not in requires:
        return []

    needed: set[str] = set()
    frontier = list(requires[node_id])
    while frontier:
        current = frontier.pop()
        if current in needed or current not in requires:
            continue
        needed.add(current)
        frontier.extend(requires[current])

    ordered = [candidate for candidate in graph.topo_order if candidate in needed]
    # Anything the order forgot still has to be reported. A short list that looks complete is worse
    # than an unordered tail: the caller has no way to tell it was handed half a chain, and the
    # whole purpose of this function is that the director gets the *whole* chain.
    return ordered + sorted(needed - set(ordered))
