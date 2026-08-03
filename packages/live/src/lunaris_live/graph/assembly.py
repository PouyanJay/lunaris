"""Deterministic assembly: the compiler proposes, this disposes.

A model is allowed to be wrong about structure — it will name a prerequisite that does not exist, or
draw a dependency loop. It is *not* allowed to assert that its own output is correct. So
``is_acyclic`` and ``topo_order`` are computed here, from the edges, and a graph is only ever marked
acyclic by code that proved it.

The structural guarantees come from ``lunaris_runtime.dag``, the same algebra Studio's
``GraphAssembler`` runs on. What lives here is the translation between Live's node model — where a
concept carries its own prerequisites — and the plain edges that algebra works in.
"""

import structlog
from lunaris_runtime.dag import remove_cycles, topological_order

from .schema import ConceptGraph, ConceptNode

logger = structlog.get_logger()


def assemble(graph: ConceptGraph) -> ConceptGraph:
    """Return ``graph`` with dangling and cyclic prerequisites removed and its order derived.

    Deterministic for a given input: the same concepts always assemble to the same order, so a
    compile is reproducible and the diff between two versions of a growing graph is readable.
    """
    known = {node.id for node in graph.nodes}
    # Drop prerequisites naming a concept that isn't in the graph. A dangling edge is the most
    # common decomposition error, and it must not be able to strand a node out of the topo order.
    # Repeats go too: "needs X, and also X" says nothing twice, and leaving duplicates in would make
    # a single dependency look like two edges to everything downstream of here.
    pruned = [node.model_copy(update={"requires": _usable(node, known)}) for node in graph.nodes]

    # Live's edges carry no strength — a prerequisite is claimed or it isn't — so no weights are
    # passed and the loop's lowest-sorting edge is spent. Only edges *inside* a cycle are ever cut.
    edges = _edges_of(pruned)
    kept = set(remove_cycles(edges))
    dropped = [edge for index, edge in enumerate(edges) if index not in kept]

    if dropped:
        pruned = _without(pruned, dropped)
        # A repair loses information, so it is reported rather than absorbed: these edges were in
        # the compiler's output and are not in the graph the learner gets.
        logger.warning(
            "live.graph.cycle_repaired",
            graph_id=graph.graph_id,
            dropped_edges=[
                {"dependent": dependent, "prerequisite": prerequisite}
                for prerequisite, dependent in dropped
            ],
        )

    # Re-derived from the corrected nodes rather than by filtering the original edges: `pruned` is
    # the single answer to "what survived", and asking it twice is how the two drift apart.
    order = topological_order([node.id for node in pruned], _edges_of(pruned))
    return graph.model_copy(update={"nodes": pruned, "topo_order": order, "is_acyclic": True})


def _edges_of(nodes: list[ConceptNode]) -> list[tuple[str, str]]:
    """The dependencies as ``(prerequisite, dependent)`` pairs — an edge points forward, from what
    you need first to what it unlocks."""
    return [(prerequisite, node.id) for node in nodes for prerequisite in node.requires]


def _usable(node: ConceptNode, known: set[str]) -> list[str]:
    """The node's prerequisites that name a real, different concept — each of them once.

    Order is preserved so the compiler's own sense of what matters most survives.
    """
    usable: list[str] = []
    for prerequisite in node.requires:
        if prerequisite in known and prerequisite != node.id and prerequisite not in usable:
            usable.append(prerequisite)
    return usable


def _without(nodes: list[ConceptNode], dropped: list[tuple[str, str]]) -> list[ConceptNode]:
    """The nodes again, minus the prerequisites the cycle repair spent."""
    by_dependent: dict[str, set[str]] = {}
    for prerequisite, dependent in dropped:
        by_dependent.setdefault(dependent, set()).add(prerequisite)
    return [
        node
        if node.id not in by_dependent
        else node.model_copy(
            update={"requires": [r for r in node.requires if r not in by_dependent[node.id]]}
        )
        for node in nodes
    ]
