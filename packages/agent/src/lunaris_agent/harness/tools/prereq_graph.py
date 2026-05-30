from collections.abc import Mapping, Sequence

from langchain_core.tools import BaseTool, tool
from lunaris_graph import PrerequisiteGraphBuilder

from ._core import build_prerequisite_graph_payload


def make_prerequisite_graph_tool(builder: PrerequisiteGraphBuilder) -> BaseTool:
    """A deterministic capability tool: order proposed concepts into a validated graph.

    The agent PROPOSES the knowledge components; this tool GUARANTEES the result — an acyclic
    graph with a topological teaching order (Failure-A moat). The guarantee lives in the
    builder, never in the model, so the agent cannot teach a concept before its prerequisite.
    The builder is injected (live Claude judge or a stub for the no-key path).
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
        return await build_prerequisite_graph_payload(builder, concepts, goal, frontier)

    return build_prerequisite_graph
