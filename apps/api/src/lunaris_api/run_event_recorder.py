import structlog
from lunaris_runtime.persistence import IRunEventStore
from lunaris_runtime.schema import RunEvent, RunEventKind

from .progress_sink import StreamItem

logger = structlog.get_logger()


class RunEventRecorder:
    """Buffers one run's streamed events and flushes them to the event log in best-effort batches.

    A per-run companion to ``CourseService.stream()``: each forwarded ``progress``/``agent`` beat is
    buffered (the closing ``course`` frame is the result, not a transcript beat, so it is skipped)
    and the buffer is flushed at a **phase boundary** (a coarse ``progress`` beat) or once it fills
    to the batch size — so a build that crashes mid-stream still replays everything up to the last
    boundary, while steady-state writes are batched rather than one DB round-trip per event. ``seq``
    is the run-scoped emission index assigned here, where the two streams interleave into one queue,
    so replay order survives without a wall clock. Persistence is best-effort: a failed flush is
    logged and swallowed, never blocking a yield or breaking a build. Events past ``cap`` are
    dropped with a single ``run_events_truncated`` note. A ``None`` store makes every method a no-op
    (the batch / no-key path).
    """

    # A run's persisted transcript is bounded: a runaway build (or a future P6 grounding sweep that
    # multiplies events) must not grow the table without limit. Past the cap we stop persisting and
    # log the truncation once — the live stream still shows everything; only replay is clipped.
    CAP_PER_RUN = 5000

    # Flush once the buffer holds this many events, so a single long phase can't buffer unboundedly.
    BATCH_SIZE = 50

    def __init__(
        self,
        store: IRunEventStore | None,
        *,
        run_id: str,
        course_id: str,
        owner_id: str | None = None,
        cap: int = CAP_PER_RUN,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        self._store = store
        self._run_id = run_id
        self._course_id = course_id
        # The owner this run's events belong to (Phase 2). None = unscoped (auth-off / single-user).
        self._owner_id = owner_id
        self._cap = cap
        self._batch_size = batch_size
        self._buffer: list[RunEvent] = []
        self._seq = 0
        self._truncated = False

    async def record(self, item: StreamItem) -> None:
        """Buffer one streamed event, flushing at a phase boundary or when the batch fills."""
        if self._store is None:
            return
        kind, payload = item
        if kind not in (RunEventKind.PROGRESS, RunEventKind.AGENT):
            return  # defensive: only the two transcript streams are persisted
        if self._seq >= self._cap:
            if not self._truncated:
                self._truncated = True
                logger.warning(
                    "run_events_truncated",
                    run_id=self._run_id,
                    course_id=self._course_id,
                    cap=self._cap,
                )
            return
        event_kind = RunEventKind(kind)
        self._buffer.append(
            RunEvent(
                run_id=self._run_id,
                course_id=self._course_id,
                seq=self._seq,
                kind=event_kind,
                payload=payload.model_dump(by_alias=True, mode="json"),
            )
        )
        self._seq += 1
        if event_kind == RunEventKind.PROGRESS or len(self._buffer) >= self._batch_size:
            await self.flush()

    async def flush(self) -> None:
        """Write the buffered batch best-effort; safe to await in a ``finally`` (does not yield)."""
        if self._store is None or not self._buffer:
            return
        # Clear before the write so a failed flush drops that batch (best-effort), never re-sends.
        batch = self._buffer
        self._buffer = []
        try:
            await self._store.append(events=batch, owner_id=self._owner_id)
        except Exception:
            logger.warning(
                "run_events_append_failed",
                run_id=self._run_id,
                course_id=self._course_id,
                exc_info=True,
            )
