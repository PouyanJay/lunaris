from collections.abc import Sequence

from .find_cycle import find_cycle


def remove_cycles(
    edges: Sequence[tuple[str, str]], *, weights: Sequence[float] | None = None
) -> list[int]:
    """Indices of the edges to keep so that what remains is acyclic.

    A prerequisite graph is a DAG; a cycle means at least one claimed dependency is wrong. Each loop
    costs exactly one edge — never the whole loop, and never an edge belonging to a concept that
    merely sits downstream of one.

    ``weights`` says which claim to disbelieve first, and the lowest-weighted edge in the cycle is
    the one spent. Studio passes its LLM-judged edge strengths, so the weakest judgment loses; ties
    there fall to whichever the cycle reached first, which is the behaviour its pipeline has always
    had.

    With no weights — Live's case, where a prerequisite is claimed or it isn't — every edge in the
    loop is equally suspect, so the choice falls to the lowest-sorting ``(source, target)`` pair.
    Note what that is *not*: the first edge the search happened to reach. Sorting on the edge itself
    means the same concepts repair the same way no matter what order the compiler emitted them in,
    which is what makes two compiles of one topic genuinely comparable.
    """
    kept = list(range(len(edges)))

    while True:
        cycle = find_cycle([edges[index] for index in kept])
        if cycle is None:
            return kept
        # `cycle` indexes into the filtered list; translate back to the caller's indices.
        original = [kept[position] for position in cycle]
        spent = (
            min(original, key=lambda index: weights[index])
            if weights
            else min(original, key=lambda index: edges[index])
        )
        kept = [index for index in kept if index != spent]
