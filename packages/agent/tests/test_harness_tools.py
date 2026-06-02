"""P1: the deterministic moats exposed as tools the agent calls. The prerequisite-graph tool
must GUARANTEE an acyclic, topological ordering regardless of how the agent proposed concepts."""

import json
from collections.abc import Callable, Sequence

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from lunaris_agent.harness import build_course_agent
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_prerequisite_graph_tool
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_runtime.schema import BloomLevel, KnowledgeComponent

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


def _draft_with_concepts() -> CourseDraft:
    draft = CourseDraft(topic="t", course_id="c", run_id="r")
    draft.concepts = [
        KnowledgeComponent(
            id=c["id"],
            label=str(c["label"]),
            definition=str(c["definition"]),
            difficulty=float(c["difficulty"]),
            bloom_ceiling=BloomLevel.APPLY,
        )
        for c in _CONCEPTS
    ]
    draft.goal_concept = "c"
    return draft


async def test_graph_tool_reads_concepts_from_the_draft() -> None:
    # Arrange — extract_concepts already recorded the concepts + goal on the draft. The agent must
    # NOT have to re-emit the array (re-threading 50+ concepts is what looped forever live).
    draft = _draft_with_concepts()
    tool = make_prerequisite_graph_tool(PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)), draft)

    # Act — call with NO concepts arg (the omitted-arg call that used to loop on 0 concepts).
    graph = await tool.ainvoke({})

    # Assert — the graph was built from the draft's concepts and recorded back on the draft.
    assert graph["isAcyclic"] is True
    assert graph["topoOrder"].index("a") < graph["topoOrder"].index("c")
    assert draft.graph is not None
    assert len(draft.graph.nodes) == len(_CONCEPTS)


async def test_graph_tool_ignores_an_empty_model_concepts_arg_when_a_draft_is_present() -> None:
    # Arrange — even if the model passes an empty concepts list (the live failure), the draft wins.
    draft = _draft_with_concepts()
    tool = make_prerequisite_graph_tool(PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)), draft)

    # Act
    graph = await tool.ainvoke({"concepts": [], "goal": ""})

    # Assert — built from the draft's 3 concepts (not the empty arg), acyclic, recorded on draft.
    assert len(graph["nodes"]) == len(_CONCEPTS)
    assert graph["isAcyclic"] is True
    assert draft.graph is not None


async def test_graph_tool_with_a_draft_but_no_concepts_raises_a_clear_error() -> None:
    # Arrange — a draft present but extract_concepts was never called (out-of-order tool use).
    draft = CourseDraft(topic="t", course_id="c", run_id="r")
    tool = make_prerequisite_graph_tool(PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)), draft)

    # Act / Assert
    with pytest.raises(ValueError, match="call extract_concepts first"):
        await tool.ainvoke({})


async def test_graph_tool_without_a_draft_still_requires_concepts() -> None:
    # Arrange — the bare-agent / direct surface has no draft, so the caller must supply concepts.
    tool = make_prerequisite_graph_tool(PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)))

    # Act / Assert
    with pytest.raises(ValueError, match="concepts are required"):
        await tool.ainvoke({"goal": "c"})
