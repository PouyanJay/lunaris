from lunaris_runtime.schema import AgentEvent


class NoOpAgentSink:
    """The default agent sink: discards every event.

    Lets the agent emit transcript events unconditionally while batch callers (tests, the
    synchronous ``POST /api/courses`` path) pay nothing and need no wiring.
    """

    async def emit(self, event: AgentEvent) -> None:
        return None
