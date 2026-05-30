import asyncio

import structlog
from lunaris_runtime.schema import Edge, KnowledgeComponent, PrerequisiteGraph

from lunaris_graph.assembler import GraphAssembler
from lunaris_graph.protocols import IPrereqJudge
from lunaris_graph.verdict import PrereqVerdict

logger = structlog.get_logger()

_DEFAULT_MAX_CONCURRENCY = 8


class PrerequisiteGraphBuilder:
    """Builds a validated prerequisite graph from knowledge components.

    LLM pairwise judgments → deterministic assembly. The judge is injected (DIP) so
    the model is swappable and tests run a deterministic stub.

    Pairwise judgments run concurrently but are capped by a semaphore so a large KC
    set (O(n²/2) pairs) doesn't burst past provider rate limits — the cost/latency
    guard the MVP plan's risk register calls for.
    """

    def __init__(
        self,
        judge: IPrereqJudge,
        assembler: GraphAssembler | None = None,
        *,
        max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
    ) -> None:
        self._judge = judge
        self._assembler = assembler or GraphAssembler()
        self._max_concurrency = max(1, max_concurrency)

    async def build(
        self, kcs: list[KnowledgeComponent], frontier: list[str], goal: str
    ) -> PrerequisiteGraph:
        assembler = self._assembler

        pairs = assembler.candidate_pairs(kcs)
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def judge_pair(
            prereq: KnowledgeComponent, dependent: KnowledgeComponent
        ) -> PrereqVerdict:
            async with semaphore:
                return await self._judge.judge(prereq, dependent)

        verdicts = await asyncio.gather(*(judge_pair(p, d) for p, d in pairs))
        edges = [
            Edge(from_=prereq.id, to=dependent.id, strength=verdict.strength)
            for (prereq, dependent), verdict in zip(pairs, verdicts, strict=True)
            if verdict.is_prereq
        ]

        edges = assembler.remove_cycles(edges)
        edges = assembler.transitive_reduction(edges)
        node_ids, edges = assembler.prune_to_frontier({k.id for k in kcs}, edges, frontier, goal)
        nodes = [k for k in kcs if k.id in node_ids]
        topo = assembler.topological_sort(nodes, edges)

        if not assembler.is_acyclic(edges):
            raise AssertionError("assembled graph is not acyclic")

        logger.info(
            "prerequisite_graph_built",
            kc_count=len(nodes),
            edge_count=len(edges),
            goal=goal,
            frontier_size=len(frontier),
        )
        return PrerequisiteGraph(
            nodes=nodes,
            edges=edges,
            frontier=list(frontier),
            is_acyclic=True,
            topo_order=topo,
        )
