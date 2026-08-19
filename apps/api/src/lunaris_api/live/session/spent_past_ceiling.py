import asyncio

import structlog
from lunaris_runtime.persistence import ISubjectCostStore, PersistenceError
from lunaris_runtime.schema import CostSubjectType

logger = structlog.get_logger()

#: How long the ledger's rollup may take to answer before the check gives up and lets the work
#: through. A telemetry outage must not end somebody's lesson, and a slow one must not stall it.
_BUDGET_CHECK_TIMEOUT_S = 1.0


async def spent_past_ceiling(
    subject_cost_store: ISubjectCostStore | None,
    *,
    session_id: str,
    owner_id: str | None,
    ceiling_usd: float,
) -> float | None:
    """What a session has spent, when that is at or past its ceiling; ``None`` otherwise.

    One reading of the ceiling for everything that spends the session's money (P2c T8): the turn,
    which refuses with a status, and the prefetch, which quietly does not ask. Read from the
    ledger's rollup rather than counted again in memory — the number already exists, and a second
    count would be a second truth. Fails **open**: a rollup that cannot be read (or read in time)
    refuses nobody, because a telemetry outage must not end somebody's lesson. ``None`` also when
    nothing is wired or the ceiling is off (0 or less).
    """
    if subject_cost_store is None or ceiling_usd <= 0:
        return None
    try:
        async with asyncio.timeout(_BUDGET_CHECK_TIMEOUT_S):
            spent = await subject_cost_store.get(
                subject_type=CostSubjectType.LIVE_SESSION,
                subject_id=session_id,
                owner_id=owner_id,
            )
    except (PersistenceError, TimeoutError):
        logger.warning("live.session.budget_unreadable", session_id=session_id, exc_info=True)
        return None
    if spent is not None and spent.total_amount >= ceiling_usd:
        return spent.total_amount
    return None
