from collections.abc import Mapping, Sequence

from langchain_core.tools import BaseTool, tool
from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_runtime.schema import BloomLevel, KnowledgeComponent


def make_prerequisite_graph_tool(builder: PrerequisiteGraphBuilder) -> BaseTool:
    """A deterministic capability tool: order proposed concepts into a validated graph.

    The agent PROPOSES the knowledge components; this tool GUARANTEES the result — an acyclic
    graph with a topological teaching order (Failure-A moat). The guarantee lives in the
    builder (deterministic assembly), never in the model, so the agent cannot teach a concept
    before its prerequisite no matter what it reasons. The builder is injected, so the live
    path uses the Claude judge and the no-key path uses a stub.
    """

    @tool
    async def build_prerequisite_graph(
        concepts: Sequence[Mapping[str, object]],
        goal: str,
        frontier: Sequence[str] | None = None,
    ) -> dict[str, object]:
        """Order knowledge components into a validated, ACYCLIC prerequisite graph.

        ``concepts`` is a list of ``{id, label, definition, difficulty}``. Returns the graph as
        ``{nodes, edges, topoOrder, isAcyclic, ...}``. ``topoOrder`` is the authoritative
        teaching sequence — always teach in that order; never reorder it yourself.
        """
        kcs = [
            KnowledgeComponent(
                id=str(concept["id"]),
                label=str(concept.get("label", concept["id"])),
                definition=str(concept.get("definition", "")),
                difficulty=float(concept.get("difficulty", 0.5)),  # type: ignore[arg-type]
                bloom_ceiling=BloomLevel.APPLY,
            )
            for concept in concepts
        ]
        graph = await builder.build(kcs, frontier=list(frontier or []), goal=goal)
        return graph.model_dump(by_alias=True)

    return build_prerequisite_graph
