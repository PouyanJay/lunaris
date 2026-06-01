"""A run-scoped progress emitter the draft-bound tools share.

The agent generates progress *inside* its tool calls, but the streamable sink is supplied by the
runner. ``ProgressReporter`` wraps the injected ``IProgressSink`` and a monotonic sequence counter,
so each tool can ``emit`` a ``ProgressEvent`` at its stage boundary without knowing the sink or
owning the ordinal. It mirrors the orchestrator's ``emit`` closure, so the agent pipeline produces
the same ordered stage trail the API already streams as SSE. The default sink is a no-op (batch
callers pay nothing).
"""

import structlog
from lunaris_runtime.schema import ProgressEvent, ProgressStage

from ..progress import IProgressSink, NoOpProgressSink
from .stage_cursor import StageCursor

logger = structlog.get_logger()


class ProgressReporter:
    """Stamps and forwards progress events for one run (one instance per :class:`CourseDraft`)."""

    def __init__(
        self, run_id: str, sink: IProgressSink | None = None, cursor: StageCursor | None = None
    ) -> None:
        self._run_id = run_id
        self._sink = sink or NoOpProgressSink()
        self._sequence = 0
        # Shared with the run's AgentReporter (when wired) so fine events bucket under the phase
        # active at their emit time; None for batch callers that don't track phases.
        self._cursor = cursor

    async def emit(self, stage: ProgressStage, label: str, **counts: object) -> None:
        """Emit one ordered event; its monotonic sequence lets clients order without a clock.

        Progress is best-effort telemetry: the sequence advances before the await and a failing sink
        is swallowed-and-logged, so a broken/disconnected stream degrades streaming without aborting
        the build (in the agent path a raised emit would surface as a tool error the model fumbles).
        """
        if self._cursor is not None:
            self._cursor.advance(stage)
        event = ProgressEvent(
            stage=stage, label=label, run_id=self._run_id, sequence=self._sequence, **counts
        )
        self._sequence += 1
        try:
            await self._sink.emit(event)
        except Exception:
            logger.warning(
                "progress_emit_failed", stage=stage.value, run_id=self._run_id, exc_info=True
            )
