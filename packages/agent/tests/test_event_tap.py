"""Unit tests for the harness event tap — the LangGraph ``updates`` stream → ``AgentEvent`` map.

Each test drives the translator with a scripted ``stream_mode="updates"`` sequence (a stand-in
compiled agent), so every mapping is asserted deterministically without a model or the deep-agent
runtime: assistant text → reasoning, tool calls → tool-call events, the planning tool → a TODO,
tool result messages → tool-result events (with ``write_todos`` suppressed on both call and result),
run_id correlation + sequencing, multi-node chunks, and content-block tool results.
"""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from lunaris_agent.harness.agent_reporter import AgentReporter
from lunaris_agent.harness.event_tap import stream_course_build
from lunaris_runtime.schema import AgentEvent, AgentEventKind


class _RecordingSink:
    """An IAgentSink that captures emitted events for assertion."""

    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


class _ScriptedUpdatesAgent:
    """A stand-in for the compiled deep agent: replays a fixed ``astream(updates)`` sequence."""

    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self._updates = updates

    async def astream(self, inputs: Any, stream_mode: str) -> AsyncIterator[dict[str, Any]]:
        assert stream_mode == "updates", f"expected 'updates', got {stream_mode!r}"
        for update in self._updates:
            yield update


async def _run(updates: list[dict[str, Any]], run_id: str = "run-x") -> _RecordingSink:
    """Drive the tap over a scripted updates stream and return the recording sink."""
    sink = _RecordingSink()
    agent = _ScriptedUpdatesAgent(updates)
    await stream_course_build(agent, {"messages": []}, AgentReporter(run_id, sink))
    return sink


async def test_event_tap_maps_assistant_text_to_reasoning() -> None:
    # Arrange / Act
    sink = await _run([{"model": {"messages": [AIMessage(content="Planning the build")]}}])

    # Assert
    assert [e.kind for e in sink.events] == [AgentEventKind.REASONING]
    assert sink.events[0].text == "Planning the build"


async def test_event_tap_maps_a_tool_call_and_its_result() -> None:
    # Arrange
    extract_call = {"name": "extract_concepts", "args": {"topic": "demo"}, "id": "t1"}
    updates: list[dict[str, Any]] = [
        {"model": {"messages": [AIMessage(content="", tool_calls=[extract_call])]}},
        {
            "tools": {
                "messages": [
                    ToolMessage(content="3 concepts", name="extract_concepts", tool_call_id="t1")
                ]
            }
        },
    ]

    # Act
    sink = await _run(updates)

    # Assert — call carries name + args; result carries name + a summary.
    call, result = sink.events
    assert call.kind is AgentEventKind.TOOL_CALL
    assert call.tool == "extract_concepts"
    assert call.tool_args == {"topic": "demo"}
    assert result.kind is AgentEventKind.TOOL_RESULT
    assert result.tool == "extract_concepts"
    assert result.result == "3 concepts"


async def test_event_tap_maps_write_todos_call_to_a_todo_and_suppresses_its_result() -> None:
    # Arrange — the planning tool, then its (suppressed) result message.
    todo_call = {
        "name": "write_todos",
        "args": {"todos": [{"content": "Extract concepts", "status": "in_progress"}]},
        "id": "p0",
    }
    updates: list[dict[str, Any]] = [
        {"model": {"messages": [AIMessage(content="", tool_calls=[todo_call])]}},
        {"tools": {"messages": [ToolMessage(content="ok", name="write_todos", tool_call_id="p0")]}},
    ]

    # Act
    sink = await _run(updates)

    # Assert — exactly one TODO event (the plan), and nothing labelled write_todos.
    assert [e.kind for e in sink.events] == [AgentEventKind.TODO]
    assert sink.events[0].todos == [{"content": "Extract concepts", "status": "in_progress"}]


async def test_event_tap_emits_reasoning_then_tool_call_for_one_message() -> None:
    # Arrange — a single assistant message carrying BOTH text and a tool call.
    message = AIMessage(
        content="Let me extract the concepts.",
        tool_calls=[{"name": "extract_concepts", "args": {}, "id": "t1"}],
    )

    # Act
    sink = await _run([{"model": {"messages": [message]}}])

    # Assert — reasoning first, then the tool call (natural transcript order).
    assert [e.kind for e in sink.events] == [AgentEventKind.REASONING, AgentEventKind.TOOL_CALL]


async def test_event_tap_ignores_empty_text_on_a_tool_only_turn() -> None:
    # Arrange — a tool-only assistant message (empty content) must not emit an empty reasoning beat.
    tool_only = AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "i"}])

    # Act
    sink = await _run([{"model": {"messages": [tool_only]}}])

    # Assert — only the tool call, no reasoning.
    assert [e.kind for e in sink.events] == [AgentEventKind.TOOL_CALL]


async def test_event_tap_stamps_run_id_and_monotonic_sequence() -> None:
    # Arrange / Act — two reasoning beats across two chunks.
    sink = await _run(
        [
            {"model": {"messages": [AIMessage(content="step one")]}},
            {"model": {"messages": [AIMessage(content="step two")]}},
        ],
        run_id="run-corr",
    )

    # Assert — every event is run-correlated and the sequence is gap-free from zero.
    assert all(e.run_id == "run-corr" for e in sink.events)
    assert [e.sequence for e in sink.events] == list(range(len(sink.events)))


async def test_event_tap_handles_a_multi_node_update_chunk() -> None:
    # Arrange — one chunk carrying deltas from two nodes at once (a valid LangGraph shape).
    chunk = {
        "model": {"messages": [AIMessage(content="thinking")]},
        "tools": {
            "messages": [ToolMessage(content="done", name="extract_concepts", tool_call_id="t1")]
        },
    }

    # Act
    sink = await _run([chunk])

    # Assert — both nodes' messages were translated.
    assert {e.kind for e in sink.events} == {
        AgentEventKind.REASONING,
        AgentEventKind.TOOL_RESULT,
    }


async def test_event_tap_renders_content_block_tool_results() -> None:
    # Arrange — a tool result whose content is text blocks, not a plain string.
    blocks = [{"type": "text", "text": "extracted 3"}, {"type": "other", "data": 1}]
    result = ToolMessage(content=blocks, name="extract_concepts", tool_call_id="t1")
    updates: list[dict[str, Any]] = [{"tools": {"messages": [result]}}]

    # Act
    sink = await _run(updates)

    # Assert — the text blocks are flattened into the result summary.
    assert sink.events[0].kind is AgentEventKind.TOOL_RESULT
    assert sink.events[0].result == "extracted 3"
