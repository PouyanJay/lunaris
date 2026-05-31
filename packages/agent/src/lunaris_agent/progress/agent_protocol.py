from typing import Protocol

from lunaris_runtime.schema import AgentEvent


class IAgentSink(Protocol):
    """A destination for the deep agent's fine-grained transcript events.

    Parallel to :class:`IProgressSink` (which carries coarse pipeline *stages*), this carries the
    Claude-grade transcript feed — reasoning, tool calls + results, todo updates. The agent pipeline
    depends only on this abstraction (DIP); concrete sinks are a no-op (the default, for batch runs)
    and an async-queue sink the API drains to stream Server-Sent Events. ``emit`` must be cheap and
    non-blocking (enqueue, never do I/O inline) — and best-effort: a failing sink must never abort a
    build.
    """

    async def emit(self, event: AgentEvent) -> None: ...
