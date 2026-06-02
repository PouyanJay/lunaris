from collections.abc import Mapping, Sequence

from langchain_core.tools import BaseTool, tool
from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_runtime.schema import ProgressStage

from ..draft import CourseDraft
from ._core import build_prerequisite_graph_payload


def make_prerequisite_graph_tool(
    builder: PrerequisiteGraphBuilder,
    draft: CourseDraft | None = None,
) -> BaseTool:
    """A deterministic capability tool: order the extracted concepts into a validated graph.

    The agent PROPOSES the knowledge components (via ``extract_concepts``); this tool GUARANTEES
    the result — an acyclic graph with a topological teaching order (Failure-A moat). The guarantee
    lives in the builder, never in the model, so the agent cannot teach a concept before its
    prerequisite. The builder is injected (live Claude judge or a stub for the no-key path). When a
    run ``draft`` is supplied (the agent pipeline), the concepts are read from the draft (where
    ``extract_concepts`` recorded them) and the typed graph is recorded back on it — so the model
    never has to re-emit the concept array and ``finalize_course`` assembles from authoritative
    data, not the model's messages (mirrors how ``design_curriculum`` reads ``draft.graph``).
    """

    @tool
    async def build_prerequisite_graph(
        concepts: Sequence[Mapping[str, object]] | None = None,
        goal: str | None = None,
        frontier: Sequence[str] | None = None,
    ) -> dict[str, object]:
        """Order the extracted knowledge components into a validated, ACYCLIC prerequisite graph.

        The concepts from ``extract_concepts`` are already available to this tool — you do NOT
        need to pass them back; just call it. Returns the graph as
        ``{nodes, edges, topoOrder, isAcyclic, ...}``. ``topoOrder`` is the authoritative teaching
        sequence — always teach in that order; never reorder it yourself.
        """
        if draft is None:
            # The bare-agent / direct-call surface: the caller supplies the concepts and goal.
            if not concepts:
                raise ValueError("concepts are required to build a prerequisite graph")
            return await build_prerequisite_graph_payload(builder, concepts, goal or "", frontier)
        # Agent pipeline: read the authoritative concepts the extractor recorded on the draft, so
        # the model never re-emits the (possibly large) array — the cause of the empty-concepts
        # retry loop on big topics where the model can't reliably re-thread 50+ concepts.
        if not draft.concepts:
            raise ValueError("no concepts on the draft — call extract_concepts first")
        # frontier is empty in the MVP agent pipeline (the novice-learner assumption).
        graph = await builder.build(
            list(draft.concepts),
            frontier=list(draft.frontier),
            goal=draft.goal_concept or goal or "",
        )
        draft.graph = graph
        await draft.progress.emit(
            ProgressStage.GRAPH_BUILT,
            f"Built prerequisite graph: {len(graph.nodes)} concepts, {len(graph.edges)} edges",
            kc_count=len(graph.nodes),
            edge_count=len(graph.edges),
        )
        return graph.model_dump(by_alias=True)

    return build_prerequisite_graph
