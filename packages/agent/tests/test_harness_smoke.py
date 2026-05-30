"""P0 smoke: the Deep Agents harness runs and calls a tool, driven deterministically by a
scripted fake model (see conftest.ScriptedChatModel) — proving the no-key CI path."""

from collections.abc import Callable, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from lunaris_agent.harness import build_course_agent


async def test_harness_plans_and_calls_a_tool_without_a_key(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
) -> None:
    # Arrange — a trivial capability tool + a scripted planner that calls it, then finishes.
    recorded: list[str] = []

    @tool
    def add_concept(concept_id: str) -> str:
        """Record a knowledge component on the course draft."""
        recorded.append(concept_id)
        return f"added {concept_id}"

    model = scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "add_concept", "args": {"concept_id": "binary_search"}, "id": "c1"}
                ],
            ),
            AIMessage(content="Added the goal concept."),
        ]
    )
    agent = build_course_agent(model, [add_concept])

    # Act
    result = await agent.ainvoke({"messages": [HumanMessage(content="add binary_search")]})

    # Assert — the agent actually invoked the tool and the result flowed back into the loop.
    assert recorded == ["binary_search"]
    assert any(isinstance(message, ToolMessage) for message in result["messages"])
    assert result["messages"][-1].content == "Added the goal concept."
