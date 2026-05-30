from collections import deque

from lunaris_runtime.schema import Edge, KnowledgeComponent


class GraphAssembler:
    """The deterministic correctness core (build-spec §07).

    The LLM judges edges; this class guarantees the structure: removes cycles,
    minimizes via transitive reduction, prunes to the frontier→goal subgraph, and
    produces a valid topological order. Every method is pure and exhaustively testable.
    """

    def candidate_pairs(
        self, kcs: list[KnowledgeComponent]
    ) -> list[tuple[KnowledgeComponent, KnowledgeComponent]]:
        """Ordered pairs to test: easier→harder only (cuts the judgment space in half)."""
        ordered = sorted(kcs, key=lambda k: (k.difficulty, k.id))
        return [(a, b) for i, a in enumerate(ordered) for b in ordered[i + 1 :]]

    def remove_cycles(self, edges: list[Edge]) -> list[Edge]:
        """A real prerequisite graph is a DAG; any cycle is a judgment error.

        Break each cycle at its weakest edge until none remain.
        """
        kept = list(edges)
        while True:
            cycle = self._find_cycle(kept)
            if cycle is None:
                return kept
            weakest = min(cycle, key=lambda e: e.strength)
            kept = [e for e in kept if e is not weakest]

    def transitive_reduction(self, edges: list[Edge]) -> list[Edge]:
        """Drop A→C when A→…→C already holds, so sequencing isn't over-constrained."""
        kept = list(edges)
        for edge in list(edges):
            if edge not in kept:
                continue
            others = [e for e in kept if e is not edge]
            if self._reachable(edge.from_, edge.to, others):
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
        difficulty = {n.id: n.difficulty for n in nodes}
        ids = set(difficulty)
        in_degree = dict.fromkeys(ids, 0)
        successors: dict[str, list[str]] = {i: [] for i in ids}
        for e in edges:
            if e.from_ in ids and e.to in ids:
                in_degree[e.to] += 1
                successors[e.from_].append(e.to)

        ready = [i for i in ids if in_degree[i] == 0]
        order: list[str] = []
        while ready:
            ready.sort(key=lambda i: (difficulty[i], i))
            current = ready.pop(0)
            order.append(current)
            for nxt in successors[current]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    ready.append(nxt)

        if len(order) != len(ids):
            raise ValueError("graph is not acyclic; cannot topologically sort")
        return order

    def is_acyclic(self, edges: list[Edge]) -> bool:
        return self._find_cycle(edges) is None

    # ── internals ────────────────────────────────────────────────

    def _adjacency(self, edges: list[Edge]) -> dict[str, list[Edge]]:
        adj: dict[str, list[Edge]] = {}
        for e in edges:
            adj.setdefault(e.from_, []).append(e)
        return adj

    def _reachable(self, src: str, dst: str, edges: list[Edge]) -> bool:
        adj = self._adjacency(edges)
        seen: set[str] = set()
        queue: deque[str] = deque(e.to for e in adj.get(src, []))
        while queue:
            node = queue.popleft()
            if node == dst:
                return True
            if node in seen:
                continue
            seen.add(node)
            queue.extend(e.to for e in adj.get(node, []))
        return False

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

    def _find_cycle(self, edges: list[Edge]) -> list[Edge] | None:
        adj = self._adjacency(edges)
        nodes: set[str] = set()
        for e in edges:
            nodes.update((e.from_, e.to))

        white, gray, black = 0, 1, 2
        color = dict.fromkeys(nodes, white)
        path: list[Edge] = []

        def visit(node: str) -> list[Edge] | None:
            color[node] = gray
            for edge in adj.get(node, []):
                nxt = edge.to
                if color.get(nxt, white) == white:
                    path.append(edge)
                    found = visit(nxt)
                    if found is not None:
                        return found
                    path.pop()
                elif color.get(nxt) == gray:
                    cycle: list[Edge] = []
                    started = False
                    for step in path:
                        started = started or step.from_ == nxt
                        if started:
                            cycle.append(step)
                    cycle.append(edge)
                    return cycle
            color[node] = black
            return None

        for start in sorted(nodes):
            if color[start] == white:
                found = visit(start)
                if found is not None:
                    return found
        return None
