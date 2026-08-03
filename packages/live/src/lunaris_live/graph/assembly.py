"""Deterministic assembly: the compiler proposes, this disposes.

A model is allowed to be wrong about structure — it will name a prerequisite that does not exist, or
draw a dependency loop. It is *not* allowed to assert that its own output is correct. So
``is_acyclic`` and ``topo_order`` are computed here, from the edges, and a graph is only ever marked
acyclic by code that proved it.

This module is Live's assembly *entry point*; T2 replaces its body with the edge algebra extracted
from Studio's ``GraphAssembler`` (the proven moat) without changing this signature.
"""

import structlog

from .schema import ConceptGraph, ConceptNode

logger = structlog.get_logger()


def assemble(graph: ConceptGraph) -> ConceptGraph:
    """Return ``graph`` with dangling and cyclic prerequisites removed and its order derived.

    Deterministic for a given input: ties are broken by id, so the same nodes always assemble to the
    same order — a compile is reproducible and a diff between two versions is readable.
    """
    known = {node.id for node in graph.nodes}
    # Drop prerequisites naming a concept that isn't in the graph. A dangling edge is the most
    # common decomposition error, and it must not be able to strand a node out of the topo order.
    pruned = [
        node.model_copy(
            update={"requires": [r for r in node.requires if r in known and r != node.id]}
        )
        for node in graph.nodes
    ]

    pruned, dropped = _break_cycles(pruned)
    ordered_ids, acyclic = _kahn(pruned)

    if dropped:
        # A repair loses information, so it is reported rather than absorbed: these edges were in
        # the compiler's output and are not in the graph the learner gets.
        logger.warning(
            "live.graph.cycle_repaired",
            graph_id=graph.graph_id,
            # Structured, not prose: a log query should be able to filter on the concepts involved
            # without parsing a sentence back apart.
            dropped_edges=[
                {"dependent": dependent, "prerequisite": prerequisite}
                for dependent, prerequisite in dropped
            ],
        )

    return graph.model_copy(
        update={"nodes": pruned, "topo_order": ordered_ids, "is_acyclic": acyclic}
    )


def _kahn(nodes: list[ConceptNode]) -> tuple[list[str], bool]:
    """Kahn's algorithm, id-sorted for reproducibility. Returns (order, is_acyclic)."""
    remaining = {node.id: set(node.requires) for node in nodes}
    order: list[str] = []

    while remaining:
        ready = sorted(node_id for node_id, needs in remaining.items() if not needs)
        if not ready:
            return order, False  # everything left is inside a cycle
        for node_id in ready:
            del remaining[node_id]
            order.append(node_id)
        for needs in remaining.values():
            needs.difference_update(ready)

    return order, True


def _break_cycles(nodes: list[ConceptNode]) -> tuple[list[ConceptNode], list[tuple[str, str]]]:
    """Remove the fewest prerequisites needed to make the graph teachable.

    A loop means the compiler was wrong about *one* of its claims, not all of them. So each repair
    cuts a single edge, and only ever an edge **inside an actual cycle** — never one belonging to a
    concept that merely depends on a looped one. That distinction matters more than it looks: node
    ids come from concept slugs, so which concepts happen to sort first is unrelated to which
    dependency is wrong, and a repair that keyed off ordering would discard real curriculum at
    random. (This is the discipline Studio's ``GraphAssembler.remove_cycles`` already follows; T2
    replaces this body with that extracted algebra.)

    Returns the repaired nodes and the ``(dependent, prerequisite)`` pairs that were spent.
    """
    requires = {node.id: list(node.requires) for node in nodes}
    dropped: list[tuple[str, str]] = []

    while (cycle := _find_cycle(requires)) is not None:
        # Every edge here is genuinely load-bearing for the loop, so any of them repairs it. Pick
        # the lowest-sorting one, so the same broken decomposition always repairs the same way.
        dependent, prerequisite = min(
            (cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))
        )
        requires[dependent].remove(prerequisite)
        dropped.append((dependent, prerequisite))

    repaired = [node.model_copy(update={"requires": requires[node.id]}) for node in nodes]
    return repaired, dropped


def _find_cycle(requires: dict[str, list[str]]) -> list[str] | None:
    """One dependency loop, as the concepts around it, or ``None`` if the graph is already acyclic.

    Depth-first search over ``dependent → prerequisite``; a grey node reached again closes a loop.
    Nodes and edges are walked in sorted order so the cycle found is the same on every run.
    """
    unvisited, in_progress, done = 0, 1, 2
    colour = dict.fromkeys(requires, unvisited)
    path: list[str] = []

    def walk(node: str) -> list[str] | None:
        colour[node] = in_progress
        path.append(node)
        for prerequisite in sorted(requires[node]):
            if colour.get(prerequisite, done) == in_progress:
                return path[path.index(prerequisite) :]
            if colour.get(prerequisite, done) == unvisited:
                found = walk(prerequisite)
                if found is not None:
                    return found
        path.pop()
        colour[node] = done
        return None

    for node in sorted(requires):
        if colour[node] == unvisited:
            found = walk(node)
            if found is not None:
                return found
    return None
