from lunaris_runtime.schema import ProgressEvent


class NoOpProgressSink:
    """The default sink: discards every event.

    Lets the orchestrator emit progress unconditionally while batch callers (tests, the
    synchronous ``POST /api/courses`` path) pay nothing and need no wiring.
    """

    async def emit(self, event: ProgressEvent) -> None:
        return None
