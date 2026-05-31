"""A run-scoped emitter for the agent's fine-grained transcript events.

Mirror of :class:`ProgressReporter` for the rich agent channel: wraps the injected
:class:`IAgentSink` and a monotonic sequence so the runner (and, in T1, the harness event tap) can
``emit`` an :class:`AgentEvent` without owning the sink or the ordinal. The default sink is a no-op,
so batch callers pay nothing; emission is best-effort and never aborts a build.
"""

import structlog
from lunaris_runtime.schema import AgentEvent, AgentEventKind

from ..progress import IAgentSink, NoOpAgentSink

logger = structlog.get_logger()


class AgentReporter:
    """Stamps and forwards agent transcript events for one run (one per :class:`CourseDraft`)."""

    def __init__(self, run_id: str, sink: IAgentSink | None = None) -> None:
        self._run_id = run_id
        self._sink = sink or NoOpAgentSink()
        self._sequence = 0

    async def emit(self, kind: AgentEventKind, **fields: object) -> None:
        """Emit one ordered agent event; its monotonic sequence lets clients order without a clock.

        Best-effort telemetry: the sequence advances before the await and a failing sink is
        swallowed-and-logged, so a broken/disconnected stream degrades the transcript without
        aborting the build.
        """
        event = AgentEvent(kind=kind, run_id=self._run_id, sequence=self._sequence, **fields)
        self._sequence += 1
        try:
            await self._sink.emit(event)
        except Exception:
            logger.warning(
                "agent_event_emit_failed", kind=kind.value, run_id=self._run_id, exc_info=True
            )
