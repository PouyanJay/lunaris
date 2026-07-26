import structlog
from lunaris_runtime.metering import CostScope
from lunaris_runtime.persistence import ICostEventStore, ICourseCostStore

from .cost_recorder import CostEventRecorder

logger = structlog.get_logger()


async def drain_cost_scope(
    scope: CostScope,
    event_store: ICostEventStore | None,
    cost_store: ICourseCostStore | None,
) -> None:
    """Persist a finished build's buffered cost entries — ledger rows + the course rollup.

    The build boundary calls this once after the build completes (best-effort): it feeds each
    ``CostEntry`` the deep pipeline priced into a ``CostEventRecorder`` (which assigns ``seq``,
    batches to the append-only ledger, and recomputes the ``course_costs`` rollup from the whole
    ledger on ``finalize``). Draining at the boundary keeps the deep ``record_cost`` calls
    synchronous and store-free; the async store I/O happens here, once. A ``None`` store pair makes
    it a no-op.

    Best-effort: the recorder already swallows ``PersistenceError`` per write, and any *other*
    metering-side failure is caught and logged here — a cost bug must never fail an otherwise-good
    build (metering is an observability concern, not part of the build's success contract).
    """
    if event_store is None or cost_store is None:
        return
    try:
        recorder = CostEventRecorder(
            event_store,
            cost_store,
            run_id=scope.run_id,
            course_id=scope.course_id,
            price_book_version=scope.price_book.version,
            owner_id=scope.owner_id,
            currency=scope.currency,
        )
        for entry in scope.entries:
            await recorder.record(
                component=entry.component,
                provider=entry.provider,
                model=entry.model,
                usage=entry.usage,
                amount=entry.amount,
                pocket=entry.pocket,
            )
        await recorder.finalize()
    except Exception:  # metering must not break a build — log and move on
        logger.warning(
            "cost_drain_failed", run_id=scope.run_id, course_id=scope.course_id, exc_info=True
        )
