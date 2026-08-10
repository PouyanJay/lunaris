from collections.abc import Mapping, Sequence


def topological_order(
    nodes: Sequence[str],
    edges: Sequence[tuple[str, str]],
    *,
    rank: Mapping[str, float] | None = None,
) -> list[str]:
    """A valid teaching order: every source before every target it points at.

    ``rank`` chooses between concepts that are equally ready to be taught. Studio ranks by
    difficulty, so a course ramps smoothly rather than jumping about; Live passes nothing and falls
    back to id order, which is arbitrary but stable — and stability is what makes two compiles of
    the same topic diffable. Ties within a rank always break by id, so the result is total.

    Raises ``ValueError`` if ``edges`` contains a cycle — deriving an order from a graph that has
    none is the one thing this must never quietly paper over.
    """
    ids = set(nodes)
    in_degree = dict.fromkeys(ids, 0)
    successors: dict[str, list[str]] = {node: [] for node in ids}
    for source, target in edges:
        # Edges naming a node outside the set are the caller's to prune; ignoring them here keeps
        # this total rather than making it fail on a graph it was handed a subset of.
        if source in ids and target in ids:
            in_degree[target] += 1
            successors[source].append(target)

    ready = [node for node in ids if in_degree[node] == 0]
    order: list[str] = []
    while ready:
        ready.sort(key=lambda node: (rank[node] if rank else 0, node))
        current = ready.pop(0)
        order.append(current)
        for nxt in successors[current]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                ready.append(nxt)

    if len(order) != len(ids):
        raise ValueError("graph is not acyclic; cannot topologically sort")
    return order
