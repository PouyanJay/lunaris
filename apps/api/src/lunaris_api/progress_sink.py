import asyncio

from lunaris_runtime.schema import ProgressEvent


class QueueProgressSink:
    """Bridges the orchestrator's progress events to the request's SSE generator.

    The orchestrator runs in a background task and calls ``emit`` at each stage; the
    event generator awaits the same queue and forwards each event. ``emit`` only enqueues
    (no I/O), so it never blocks the pipeline.
    """

    def __init__(self, queue: asyncio.Queue[ProgressEvent]) -> None:
        self._queue = queue

    async def emit(self, event: ProgressEvent) -> None:
        await self._queue.put(event)
