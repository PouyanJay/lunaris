from typing import Protocol

from lunaris_runtime.schema import ProgressEvent


class IProgressSink(Protocol):
    """A destination for orchestrator progress events (build-spec: live progress).

    The orchestrator depends only on this abstraction (DIP); concrete sinks include a
    no-op (the default, for batch runs) and an async-queue sink the API drains to stream
    Server-Sent Events. ``emit`` is awaited at every stage boundary, so implementations
    must be cheap and non-blocking (enqueue, don't do I/O inline).
    """

    async def emit(self, event: ProgressEvent) -> None: ...
