from collections import deque
from collections.abc import Sequence


def is_reachable(source: str, target: str, edges: Sequence[tuple[str, str]]) -> bool:
    """Whether ``target`` can be reached from ``source`` by following ``edges``.

    Used to answer "is this edge redundant?" — if the path already exists without it, the direct
    edge only over-constrains the ordering.
    """
    adjacency: dict[str, list[str]] = {}
    for edge_source, edge_target in edges:
        adjacency.setdefault(edge_source, []).append(edge_target)

    seen: set[str] = set()
    queue: deque[str] = deque(adjacency.get(source, []))
    while queue:
        node = queue.popleft()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacency.get(node, []))
    return False
