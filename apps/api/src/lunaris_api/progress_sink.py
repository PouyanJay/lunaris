import asyncio
from typing import TYPE_CHECKING

from lunaris_runtime.schema import AgentEvent, ProgressEvent

if TYPE_CHECKING:
    from .run_event_recorder import RunEventRecorder

# A streamed item the service forwards to the SSE generator: the SSE event-name + its payload.
# The progress and agent sinks both enqueue tagged tuples onto one queue so a single drain loop
# preserves their interleaved order as the build emits them.
StreamItem = tuple[str, ProgressEvent | AgentEvent]


class _QueueSink:
    """Shared base for the two build-event sinks: enqueue a tagged beat for the live SSE viewer and,
    when a ``recorder`` is wired, record it to the durable run-events log.

    Recording follows the pipeline (the durable build task that owns these sinks), NOT the viewer
    that drains the queue — so the build log stays complete even after the client disconnects: the
    build keeps emitting and the sink keeps recording. The recorder is buffered + best-effort, so
    its I/O at phase boundaries is small and never fails the build. Subclasses only fix the tag.
    """

    def __init__(
        self, queue: asyncio.Queue[StreamItem], recorder: "RunEventRecorder | None" = None
    ) -> None:
        self._queue = queue
        self._recorder = recorder

    async def _put(self, item: StreamItem) -> None:
        await self._queue.put(item)
        if self._recorder is not None:
            await self._recorder.record(item)


class QueueProgressSink(_QueueSink):
    """Bridges the pipeline's coarse stage events to the request's SSE generator. The pipeline runs
    in a background task and calls ``emit`` at each stage; the event generator awaits the shared
    queue and forwards each item (see ``_QueueSink`` for the durable-recording contract)."""

    async def emit(self, event: ProgressEvent) -> None:
        await self._put(("progress", event))


class QueueAgentSink(_QueueSink):
    """Bridges the agent's fine-grained transcript events (reasoning / tool calls / todos) to the
    SSE generator, onto the same queue as the stage events so order is preserved. Shares the build's
    ``recorder`` with the progress sink so the two interleaved streams record under one ``seq``."""

    async def emit(self, event: AgentEvent) -> None:
        await self._put(("agent", event))
