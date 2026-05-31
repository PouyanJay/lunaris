"""Translate the deep agent's LangGraph stream into :class:`AgentEvent`s.

Taps ``CompiledStateGraph.astream(stream_mode="updates")`` and maps each step the harness takes onto
the fine-grained transcript channel the UI renders:

- an assistant message's text → ``REASONING``,
- its tool calls → ``TOOL_CALL`` (name + args), except the planning tool (``write_todos``) which
  surfaces as ``TODO`` (the live plan, as ``{content, status}`` items), and
- each tool's result message → ``TOOL_RESULT`` (name + a compact summary).

``updates`` mode is deliberate: it streams *state deltas* (the messages each node appends) while the
model node still runs via ``ainvoke``. That keeps the deterministic no-key path working — token
streaming (``astream_events`` / ``stream_mode="messages"``) forces the model into streaming mode,
which the scripted fake model cannot satisfy for tool-call-only turns. It also drives the graph to
completion exactly as ``ainvoke`` would, so the finalized course is read from the draft afterward.
Emission is best-effort (the reporter swallows sink failures), so a disconnected stream degrades the
transcript without aborting the build.
"""

from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from lunaris_runtime.schema import AgentEventKind

from .agent_reporter import AgentReporter

_TODO_TOOL = "write_todos"
_MAX_RESULT_CHARS = 600


class IStreamableAgent(Protocol):
    """The slice of a compiled LangGraph the tap needs: an ``updates``-mode async event stream.

    A structural Protocol (not the concrete ``CompiledStateGraph``) so the tap is unit-testable with
    a lightweight scripted stand-in, while real callers pass the harness graph unchanged.
    """

    def astream(
        self, inputs: Mapping[str, Any], stream_mode: str
    ) -> AsyncIterator[Mapping[str, Any]]: ...


async def stream_course_build(
    agent: IStreamableAgent, inputs: Mapping[str, Any], reporter: AgentReporter
) -> None:
    """Drive ``agent`` over ``inputs`` and emit each harness step as an :class:`AgentEvent`."""
    async for update in agent.astream(inputs, stream_mode="updates"):
        if not isinstance(update, Mapping):
            continue
        for message in _iter_messages(update):
            await _emit_message(message, reporter)


async def _emit_message(message: BaseMessage, reporter: AgentReporter) -> None:
    if isinstance(message, ToolMessage):
        # Anonymous results (no name) still surface — with an empty tool — rather than vanish; the
        # planning tool's result is the one exception, since its plan already rode the TOOL_CALL.
        if message.name == _TODO_TOOL:
            return
        await reporter.emit(
            AgentEventKind.TOOL_RESULT, tool=message.name or "", result=_compact(message.content)
        )
        return
    if isinstance(message, AIMessage):
        text = _text_of(message.content)
        if text:
            await reporter.emit(AgentEventKind.REASONING, text=text)
        for call in message.tool_calls or []:
            name = call.get("name") or ""
            args = _as_dict(call.get("args"))
            if name == _TODO_TOOL:
                todos = _normalize_todos(args.get("todos"))
                if todos:
                    await reporter.emit(AgentEventKind.TODO, todos=todos)
            else:
                await reporter.emit(AgentEventKind.TOOL_CALL, tool=name, tool_args=args)


def _iter_messages(update: Mapping[str, Any]) -> Iterator[BaseMessage]:
    """Yield each message any node appended in this ``updates`` chunk.

    A chunk is ``{node: state_delta}`` and may carry more than one node; each delta is a state
    mapping (or a list of them) whose ``messages`` is one message or a list of messages.
    """
    for node_output in update.values():
        for delta in node_output if isinstance(node_output, list) else [node_output]:
            if not isinstance(delta, Mapping):
                continue
            messages = delta.get("messages")
            if isinstance(messages, BaseMessage):
                yield messages
            elif isinstance(messages, list):
                yield from (m for m in messages if isinstance(m, BaseMessage))


def _text_of(content: Any, *, fallback: str = "") -> str:
    """Plain text from message/tool content (a string or ``text`` blocks); ``fallback`` if none."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        joined = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, Mapping) and block.get("type") == "text"
        )
        if joined or not fallback:
            return joined
    return fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalize_todos(todos: Any) -> list[dict[str, str]]:
    """Coerce the planning tool's todos into the wire shape: ``[{content, status}]``."""
    if not isinstance(todos, list):
        return []
    return [
        {"content": str(item.get("content", "")), "status": str(item.get("status", ""))}
        for item in todos
        if isinstance(item, Mapping)
    ]


def _compact(content: Any) -> str:
    """Render a tool result as a short string summary, truncated for the transcript."""
    text = _text_of(content, fallback=str(content)).strip()
    if len(text) > _MAX_RESULT_CHARS:
        return text[:_MAX_RESULT_CHARS] + "…"
    return text
