"""Unit tests for the harness event tap — the LangGraph ``updates`` stream → ``AgentEvent`` map.

Each test drives the translator with a scripted ``stream_mode="updates"`` sequence (a stand-in
compiled agent), so every mapping is asserted deterministically without a model or the deep-agent
runtime: assistant text → reasoning, tool calls → tool-call events, the planning tool → a TODO,
tool result messages → tool-result events (with ``write_todos`` suppressed on both call and result),
run_id correlation + sequencing, multi-node chunks, and content-block tool results.
"""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
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


class _ScriptedMultiModeAgent:
    """A stand-in compiled agent replaying a fixed ``astream(["updates","messages"])`` sequence.

    Each item is a ``(mode, data)`` tuple — the shape LangGraph yields when ``stream_mode`` is a
    list: ``("updates", {node: delta})`` and ``("messages", (message_chunk, metadata))``.
    """

    def __init__(self, items: list[tuple[str, Any]]) -> None:
        self._items = items

    async def astream(self, inputs: Any, stream_mode: Any) -> AsyncIterator[tuple[str, Any]]:
        assert stream_mode == ["updates", "messages"], f"expected multi-mode, got {stream_mode!r}"
        for item in self._items:
            yield item


async def _run(updates: list[dict[str, Any]], run_id: str = "run-x") -> _RecordingSink:
    """Drive the tap over a scripted updates stream and return the recording sink."""
    sink = _RecordingSink()
    agent = _ScriptedUpdatesAgent(updates)
    await stream_course_build(agent, {"messages": []}, AgentReporter(run_id, sink))
    return sink


async def _run_tokens(items: list[tuple[str, Any]], run_id: str = "run-x") -> _RecordingSink:
    """Drive the tap in token-streaming mode over a scripted multi-mode stream."""
    sink = _RecordingSink()
    agent = _ScriptedMultiModeAgent(items)
    await stream_course_build(
        agent, {"messages": []}, AgentReporter(run_id, sink), stream_tokens=True
    )
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


async def test_event_tap_streams_token_deltas_and_suppresses_the_duplicate_full_text() -> None:
    # Arrange — the model narrates token-by-token via the messages stream, then the SAME assistant
    # message arrives whole on the updates stream (text + a tool call). Its text already streamed,
    # so it must NOT re-emit as a complete reasoning beat; only its tool call rides updates.
    full = AIMessage(
        content="Let me extract.",
        tool_calls=[{"name": "extract_concepts", "args": {"topic": "x"}, "id": "t1"}],
    )
    items: list[tuple[str, Any]] = [
        ("messages", (AIMessageChunk(content="Let me "), {"langgraph_node": "model"})),
        ("messages", (AIMessageChunk(content="extract."), {"langgraph_node": "model"})),
        ("updates", {"model": {"messages": [full]}}),
    ]

    # Act
    sink = await _run_tokens(items)

    # Assert — two streaming reasoning deltas (carried on `delta`, not `text`), then the tool call.
    assert [e.kind for e in sink.events] == [
        AgentEventKind.REASONING,
        AgentEventKind.REASONING,
        AgentEventKind.TOOL_CALL,
    ]
    # The two chunks arrive as separate deltas (the frontend stitches them into one growing beat).
    assert [e.delta for e in sink.events[:2]] == ["Let me ", "extract."]
    # The full text never double-emits as a `text` reasoning beat in token mode.
    assert all(e.text is None for e in sink.events)
    assert sink.events[2].tool == "extract_concepts"
    assert sink.events[2].tool_args == {"topic": "x"}


async def test_event_tap_token_mode_drops_a_full_text_message_with_no_tool_calls() -> None:
    # Arrange — a pure-text assistant turn (no tool calls): it streams as deltas, then the same
    # whole message rides the updates stream. The updates copy must be fully suppressed (zero
    # events), so the reasoning never doubles even with no tool call to carry from the updates side.
    items: list[tuple[str, Any]] = [
        ("messages", (AIMessageChunk(content="I have "), {"langgraph_node": "model"})),
        ("messages", (AIMessageChunk(content="planned it."), {"langgraph_node": "model"})),
        ("updates", {"model": {"messages": [AIMessage(content="I have planned it.")]}}),
    ]

    # Act
    sink = await _run_tokens(items)

    # Assert — only the two streaming deltas; the whole-text updates copy emitted nothing.
    assert [e.kind for e in sink.events] == [AgentEventKind.REASONING, AgentEventKind.REASONING]
    assert [e.delta for e in sink.events] == ["I have ", "planned it."]


async def test_event_tap_token_mode_ignores_tool_call_chunks_and_streamed_tool_messages() -> None:
    # Arrange — the messages stream also carries tool-call arg deltas (empty text) and streamed tool
    # results; neither is reasoning. The structured result is read from the updates stream instead.
    tool_call_chunk = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "x", "args": "{}", "id": "t", "index": 0}],
    )
    streamed_tool = ToolMessage(content="streamed", name="extract_concepts", tool_call_id="t")
    items: list[tuple[str, Any]] = [
        ("messages", (tool_call_chunk, {"langgraph_node": "model"})),
        ("messages", (streamed_tool, {"langgraph_node": "tools"})),
        (
            "updates",
            {
                "tools": {
                    "messages": [
                        ToolMessage(content="3 concepts", name="extract_concepts", tool_call_id="t")
                    ]
                }
            },
        ),
    ]

    # Act
    sink = await _run_tokens(items)

    # Assert — only the one structured tool result; no spurious reasoning from the messages stream.
    assert [e.kind for e in sink.events] == [AgentEventKind.TOOL_RESULT]
    assert sink.events[0].result == "3 concepts"


async def test_event_tap_token_mode_still_maps_todos_from_the_updates_stream() -> None:
    # Arrange — the planning tool still surfaces as a TODO via updates while reasoning streams.
    todo_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_todos",
                "args": {"todos": [{"content": "Extract concepts", "status": "in_progress"}]},
                "id": "p0",
            }
        ],
    )
    items: list[tuple[str, Any]] = [
        ("messages", (AIMessageChunk(content="Planning…"), {"langgraph_node": "model"})),
        ("updates", {"model": {"messages": [todo_call]}}),
    ]

    # Act
    sink = await _run_tokens(items)

    # Assert — the streamed reasoning delta, then the plan (todos); write_todos itself stays hidden.
    assert [e.kind for e in sink.events] == [AgentEventKind.REASONING, AgentEventKind.TODO]
    assert sink.events[0].delta == "Planning…"
    assert sink.events[1].todos == [{"content": "Extract concepts", "status": "in_progress"}]
