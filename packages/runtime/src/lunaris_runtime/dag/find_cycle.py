from collections.abc import Sequence

_UNVISITED, _IN_PROGRESS, _DONE = 0, 1, 2


def find_cycle(edges: Sequence[tuple[str, str]]) -> list[int] | None:
    """One dependency loop as edge indices, or ``None`` if ``edges`` is already acyclic.

    Edges are ``(source, target)`` pairs and are referred to by **index** throughout this package:
    two structurally identical edges are still two distinct edges, and callers map indices back to
    their own richer edge objects. Passing the pairs themselves would silently collapse duplicates.

    Depth-first search; a node reached again while still on the stack closes the loop. Start nodes
    are visited in sorted order and each node's out-edges in list order, so the same input always
    yields the same cycle.
    """
    adjacency, nodes = _adjacency(edges)
    colour = dict.fromkeys(nodes, _UNVISITED)
    path: list[int] = []

    def visit(node: str) -> list[int] | None:
        colour[node] = _IN_PROGRESS
        for index in adjacency.get(node, []):
            target = edges[index][1]
            if colour.get(target, _UNVISITED) == _IN_PROGRESS:
                return _loop_from(target, path, index, edges)
            if colour.get(target, _UNVISITED) == _UNVISITED:
                path.append(index)
                found = visit(target)
                if found is not None:
                    return found
                path.pop()
        colour[node] = _DONE
        return None

    for start in sorted(nodes):
        if colour[start] == _UNVISITED:
            found = visit(start)
            if found is not None:
                return found
    return None


def _adjacency(edges: Sequence[tuple[str, str]]) -> tuple[dict[str, list[int]], set[str]]:
    """Out-edge indices per source, and every node the edges mention."""
    adjacency: dict[str, list[int]] = {}
    nodes: set[str] = set()
    for index, (source, target) in enumerate(edges):
        adjacency.setdefault(source, []).append(index)
        nodes.update((source, target))
    return adjacency, nodes


def _loop_from(
    closing: str, path: list[int], closing_index: int, edges: Sequence[tuple[str, str]]
) -> list[int]:
    """The cycle itself: the walked path from where ``closing`` was first left, plus the edge back.

    The path leading *into* the loop is dropped — those edges are not part of it, and treating them
    as though they were is how a repair ends up spending an edge that was never at fault.
    """
    for position, step in enumerate(path):
        if edges[step][0] == closing:
            return [*path[position:], closing_index]
    return [closing_index]
