from collections import deque

from lunaris_runtime.dag import find_cycle, is_reachable, remove_cycles, topological_order
from lunaris_runtime.schema import Edge, KnowledgeComponent


class GraphAssembler:
    """The deterministic correctness core (build-spec §07).

    The LLM judges edges; this class guarantees the structure: removes cycles,
    minimizes via transitive reduction, prunes to the frontier→goal subgraph, and
    produces a valid topological order. Every method is pure and exhaustively testable.

    The structural algebra itself lives in ``lunaris_runtime.dag`` — Lunaris Live needs the same
    guarantees over its own node model, and one implementation means a fix reaches both products.
    What stays here is what is genuinely Studio's: the difficulty ordering, the LLM-judged edge
    strength that decides which claim to disbelieve first, and the frontier→goal pruning.
    """

    def candidate_pairs(
        self, kcs: list[KnowledgeComponent]
    ) -> list[tuple[KnowledgeComponent, KnowledgeComponent]]:
        """Ordered pairs to test: easier→harder only (cuts the judgment space in half)."""
        ordered = sorted(kcs, key=lambda k: (k.difficulty, k.id))
        return [(a, b) for i, a in enumerate(ordered) for b in ordered[i + 1 :]]

    def remove_cycles(self, edges: list[Edge]) -> list[Edge]:
        """A real prerequisite graph is a DAG; any cycle is a judgment error.

        Break each cycle at its weakest edge until none remain — the least confident judgment is the
        one most likely to be the wrong one.
        """
        kept = remove_cycles(self._pairs(edges), weights=[e.strength for e in edges])
        return [edges[index] for index in kept]

    def transitive_reduction(self, edges: list[Edge]) -> list[Edge]:
        """Drop A→C when A→…→C already holds, so sequencing isn't over-constrained."""
        kept = list(edges)
        for edge in list(edges):
            if edge not in kept:
                continue
            others = [e for e in kept if e is not edge]
            if is_reachable(edge.from_, edge.to, self._pairs(others)):
                kept = others
        return kept

    def prune_to_frontier(
        self, node_ids: set[str], edges: list[Edge], frontier: list[str], goal: str
    ) -> tuple[set[str], list[Edge]]:
        """Keep only what the learner needs: prereqs of the goal not already known.

        This is the auto-leveling step — same global graph, different subgraph above
        each learner's frontier.
        """
        needed = self._ancestors(goal, edges) | {goal}
        known: set[str] = set(frontier)
        for known_id in frontier:
            known |= self._ancestors(known_id, edges)
        kept_ids = {n for n in node_ids if n in needed and n not in known}
        kept_ids.add(goal)
        kept_edges = [e for e in edges if e.from_ in kept_ids and e.to in kept_ids]
        return kept_ids, kept_edges

    def topological_sort(self, nodes: list[KnowledgeComponent], edges: list[Edge]) -> list[str]:
        """Validated teaching order. Tie-break by difficulty for a smooth ramp (ZPD)."""
        return topological_order(
            [n.id for n in nodes], self._pairs(edges), rank={n.id: n.difficulty for n in nodes}
        )

    def is_acyclic(self, edges: list[Edge]) -> bool:
        return find_cycle(self._pairs(edges)) is None

    # ── internals ────────────────────────────────────────────────

    @staticmethod
    def _pairs(edges: list[Edge]) -> list[tuple[str, str]]:
        """Studio's edges as the plain pairs the shared algebra works in."""
        return [(e.from_, e.to) for e in edges]

    def _ancestors(self, target: str, edges: list[Edge]) -> set[str]:
        """All nodes with a path to ``target`` (its transitive prerequisites)."""
        reverse: dict[str, list[str]] = {}
        for e in edges:
            reverse.setdefault(e.to, []).append(e.from_)
        seen: set[str] = set()
        queue: deque[str] = deque(reverse.get(target, []))
        while queue:
            node = queue.popleft()
            if node in seen:
                continue
            seen.add(node)
            queue.extend(reverse.get(node, []))
        return seen
