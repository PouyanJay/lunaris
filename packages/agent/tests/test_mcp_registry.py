"""P1c: the MCP capability registry exposes the deterministic moats as tools, callable over the
MCP protocol surface — the same guarantees as the in-process tools, for external MCP clients."""

from lunaris_agent.mcp_registry import build_mcp_server
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.schema import Citation

_EDGES = [("a", "c"), ("b", "c")]


def _server() -> object:
    builder = PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES))

    def retrieve(claim: str) -> list[Evidence]:
        if "binary" in claim.lower():
            return [Evidence(citation=Citation(id="src::bs", snippet=claim), score=0.9)]
        return []

    verifier = Verifier(StubEvidenceRetriever(retrieve), StubSupportAssessor())
    return build_mcp_server(builder, verifier, name="lunaris-test")


async def test_registry_lists_the_moat_tools() -> None:
    tools = await _server().list_tools()

    assert {"build_prerequisite_graph", "verify_claims"} <= {tool.name for tool in tools}


async def test_registry_graph_tool_guarantees_topological_order() -> None:
    # Act — call over the MCP surface; call_tool returns (content_blocks, structured_result).
    _content, graph = await _server().call_tool(
        "build_prerequisite_graph",
        {"concepts": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "goal": "c"},
    )

    # Assert — the moat holds across the registry boundary.
    assert graph["isAcyclic"] is True
    assert graph["topoOrder"].index("a") < graph["topoOrder"].index("c")
    assert graph["topoOrder"].index("b") < graph["topoOrder"].index("c")


async def test_registry_verify_tool_enforces_publish_gate() -> None:
    _content, verdict = await _server().call_tool(
        "verify_claims",
        {"claims": ["Binary search needs sorted input", "The earth is flat"]},
    )

    status = {row["text"]: row["status"] for row in verdict["results"]}
    assert status["Binary search needs sorted input"] == "supported"
    assert status["The earth is flat"] == "cut"
