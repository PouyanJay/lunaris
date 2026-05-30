"""P1: the deterministic moats exposed as tools the agent calls. The prerequisite-graph tool
must GUARANTEE an acyclic, topological ordering regardless of how the agent proposed concepts."""

import json
from collections.abc import Callable, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from lunaris_agent.harness import build_course_agent
from lunaris_agent.harness.tools import make_prerequisite_graph_tool
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge

# Two prerequisites of "c"; "a" and "b" are independent roots.
_EDGES = [("a", "c"), ("b", "c")]
_CONCEPTS = [
    {"id": "a", "label": "A", "definition": "first", "difficulty": 0.1},
    {"id": "b", "label": "B", "definition": "second", "difficulty": 0.2},
    {"id": "c", "label": "C", "definition": "goal", "difficulty": 0.5},
]


async def test_prereq_graph_tool_guarantees_topological_order() -> None:
    # Arrange — the tool over a deterministic stub judge (no key).
    tool = make_prerequisite_graph_tool(PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)))

    # Act — call the tool directly with concepts in a deliberately wrong order.
    graph = await tool.ainvoke({"concepts": _CONCEPTS, "goal": "c"})

    # Assert — the moat holds: acyclic, and prerequisites precede the goal in topoOrder.
    assert graph["isAcyclic"] is True
    topo = graph["topoOrder"]
    assert topo.index("a") < topo.index("c")
    assert topo.index("b") < topo.index("c")


async def test_agent_orders_concepts_via_the_graph_tool(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
) -> None:
    # Arrange — the agent proposes concepts and calls the deterministic graph tool.
    tool = make_prerequisite_graph_tool(PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)))
    model = scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "build_prerequisite_graph",
                        "args": {"concepts": _CONCEPTS, "goal": "c"},
                        "id": "g1",
                    }
                ],
            ),
            AIMessage(content="Ordered the concepts."),
        ]
    )
    agent = build_course_agent(model, [tool])

    # Act
    result = await agent.ainvoke({"messages": [HumanMessage(content="order these concepts")]})

    # Assert — the tool ran in the loop and returned a valid, acyclic graph to the agent.
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages
    payload = tool_messages[-1].content
    graph = json.loads(payload) if isinstance(payload, str) else payload
    assert graph["isAcyclic"] is True
    assert graph["topoOrder"].index("a") < graph["topoOrder"].index("c")
