import asyncio

from lunaris_runtime.schema import AgentEvent, ProgressEvent

# A streamed item the service forwards to the SSE generator: the SSE event-name + its payload.
# The progress and agent sinks both enqueue tagged tuples onto one queue so a single drain loop
# preserves their interleaved order as the build emits them.
StreamItem = tuple[str, ProgressEvent | AgentEvent]


class QueueProgressSink:
    """Bridges the pipeline's coarse stage events to the request's SSE generator.

    The pipeline runs in a background task and calls ``emit`` at each stage; the event generator
    awaits the shared queue and forwards each item. ``emit`` only enqueues (no I/O), so it never
    blocks the pipeline.
    """

    def __init__(self, queue: asyncio.Queue[StreamItem]) -> None:
        self._queue = queue

    async def emit(self, event: ProgressEvent) -> None:
        await self._queue.put(("progress", event))


class QueueAgentSink:
    """Bridges the agent's fine-grained transcript events (reasoning / tool calls / todos) to the
    SSE generator, onto the same queue as the stage events so order is preserved."""

    def __init__(self, queue: asyncio.Queue[StreamItem]) -> None:
        self._queue = queue

    async def emit(self, event: AgentEvent) -> None:
        await self._queue.put(("agent", event))
