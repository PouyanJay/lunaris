from datetime import UTC, datetime

import structlog
from lunaris_runtime.persistence import (
    ICostEventStore,
    ICourseCostStore,
    PersistenceError,
)
from lunaris_runtime.schema import CostEvent, CostPocket, CostProvider, CourseCost

logger = structlog.get_logger()


class CostEventRecorder:
    """Buffers one run's cost events and flushes them to the ledger, then rolls the course total up.

    The cost twin of ``RunEventRecorder``: each paid (or metered) call during a build is buffered
    as a ``CostEvent`` (``seq`` assigned here, run-scoped) and flushed in best-effort batches — a
    failed cost write is logged and swallowed, never blocking a yield or breaking a build.
    ``finalize`` flushes the tail, then recomputes the ``course_costs`` rollup by summing the
    course's whole ledger (so it aggregates across the build run and the separate video/cover jobs,
    and re-recording is idempotent) and upserts it.

    A ``None`` store pair makes every method a no-op (the batch / no-key path). Events past ``cap``
    are dropped with a single ``cost_events_truncated`` note.
    """

    CAP_PER_RUN = 5000
    BATCH_SIZE = 50

    def __init__(
        self,
        event_store: ICostEventStore | None,
        cost_store: ICourseCostStore | None,
        *,
        run_id: str,
        course_id: str,
        price_book_version: str,
        owner_id: str | None = None,
        currency: str = "USD",
        cap: int = CAP_PER_RUN,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        self._event_store = event_store
        self._cost_store = cost_store
        self._run_id = run_id
        self._course_id = course_id
        self._price_book_version = price_book_version
        self._owner_id = owner_id
        self._currency = currency
        self._cap = cap
        self._batch_size = batch_size
        self._buffer: list[CostEvent] = []
        self._seq = 0
        self._truncated = False

    async def record(
        self,
        *,
        component: str,
        provider: CostProvider,
        model: str | None,
        usage: dict[str, object],
        amount: float,
        pocket: CostPocket,
    ) -> None:
        """Buffer one metered call's cost, flushing when the batch fills."""
        if self._event_store is None:
            return
        if self._seq >= self._cap:
            if not self._truncated:
                self._truncated = True
                logger.warning(
                    "cost_events_truncated",
                    run_id=self._run_id,
                    course_id=self._course_id,
                    cap=self._cap,
                )
            return
        self._buffer.append(
            CostEvent(
                run_id=self._run_id,
                course_id=self._course_id,
                seq=self._seq,
                component=component,
                provider=provider,
                model=model,
                pocket=pocket,
                usage=usage,
                amount=amount,
                currency=self._currency,
                price_book_version=self._price_book_version,
            )
        )
        self._seq += 1
        if len(self._buffer) >= self._batch_size:
            await self.flush()

    async def flush(self) -> None:
        """Write the buffered batch best-effort; safe to await in a ``finally`` (does not yield)."""
        if self._event_store is None or not self._buffer:
            return
        batch = self._buffer
        self._buffer = []
        try:
            await self._event_store.append(events=batch, owner_id=self._owner_id)
        except PersistenceError:
            logger.warning(
                "cost_events_append_failed",
                run_id=self._run_id,
                course_id=self._course_id,
                exc_info=True,
            )

    async def finalize(self) -> None:
        """Flush the tail, then recompute + upsert the course rollup from the whole ledger.

        Best-effort like ``flush``: a failed rollup is logged and swallowed. Recomputing from the
        ledger (not just this run's buffer) is what makes the total aggregate the build + video +
        cover jobs and stay correct across re-records.
        """
        await self.flush()
        if self._event_store is None or self._cost_store is None:
            return
        try:
            events = await self._event_store.list_for_course(
                course_id=self._course_id, owner_id=self._owner_id
            )
            rollup = self._roll_up(events)
            await self._cost_store.upsert(cost=rollup, owner_id=self._owner_id)
        except PersistenceError:
            logger.warning(
                "course_cost_rollup_failed",
                run_id=self._run_id,
                course_id=self._course_id,
                exc_info=True,
            )

    def _roll_up(self, events: list[CostEvent]) -> CourseCost:
        """Sum the ledger into the materialized total + breakdown the Overview reads."""
        total = sum(event.amount for event in events)
        by_component: dict[str, float] = {}
        by_provider: dict[str, float] = {}
        by_pocket: dict[str, float] = {
            CostPocket.USER_KEY.value: 0.0,
            CostPocket.PLATFORM.value: 0.0,
        }
        for event in events:
            by_component[event.component] = by_component.get(event.component, 0.0) + event.amount
            key = event.provider.value
            by_provider[key] = by_provider.get(key, 0.0) + event.amount
            by_pocket[event.pocket.value] += event.amount
        breakdown: dict[str, object] = {
            "byComponent": by_component,
            "byProvider": by_provider,
            "byPocket": by_pocket,
            "eventCount": len(events),
        }
        return CourseCost(
            course_id=self._course_id,
            total_amount=total,
            currency=self._currency,
            breakdown=breakdown,
            price_book_version=self._price_book_version,
            updated_at=datetime.now(UTC),
        )
