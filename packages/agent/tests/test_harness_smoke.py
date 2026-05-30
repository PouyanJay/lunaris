"""P0 smoke: the Deep Agents harness runs and calls a tool, driven deterministically by a
scripted fake model — proving the no-key CI path for the agent core."""

from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from lunaris_agent.harness import build_course_agent


class ScriptedChatModel(GenericFakeChatModel):
    """A fake chat model that replays a scripted message list and accepts ``bind_tools``.

    The agent factory binds tools to the model before invoking it; the stock fake raises on
    ``bind_tools``. Returning ``self`` lets us drive the real harness (plan → tool call → finish)
    with a fixed script and no API key — the deterministic CI driver for the agent loop.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":  # type: ignore[override]
        return self


async def test_harness_plans_and_calls_a_tool_without_a_key() -> None:
    # Arrange — a trivial capability tool + a scripted planner that calls it, then finishes.
    recorded: list[str] = []

    @tool
    def add_concept(concept_id: str) -> str:
        """Record a knowledge component on the course draft."""
        recorded.append(concept_id)
        return f"added {concept_id}"

    model = ScriptedChatModel(
        messages=iter(
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
    )
    agent = build_course_agent(model, [add_concept])

    # Act
    result = await agent.ainvoke({"messages": [HumanMessage(content="add binary_search")]})

    # Assert — the agent actually invoked the tool and the result flowed back into the loop.
    assert recorded == ["binary_search"]
    assert any(isinstance(message, ToolMessage) for message in result["messages"])
    assert result["messages"][-1].content == "Added the goal concept."
