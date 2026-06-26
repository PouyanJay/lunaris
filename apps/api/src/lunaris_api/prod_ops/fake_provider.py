from datetime import date, datetime, time, timedelta

from .compute import ComputePoint, ComputeSeries
from .cost import CostPoint, CostSeries
from .summary import ProdOpsSummary

# A fixed anchor so the fake's series is deterministic (tests assert on it; the no-Azure path shows
# clearly synthetic data). The real adapter keys off the actual calendar.
_ANCHOR = date(2026, 6, 26)


class FakeProdOpsProvider:
    """A deterministic ``IProdOpsProvider`` for tests and the no-Azure path.

    Returns canned data — no Azure calls — so the router, admin gate, and web section can be
    exercised hermetically. The default summary covers ``rg-lunaris-prod`` in CAD, matching the live
    environment the real adapter reports on; the cost series is a stable synthetic ramp ending at a
    fixed anchor day (the most recent day flagged partial, as the real data lags).
    """

    def __init__(self, summary: ProdOpsSummary | None = None) -> None:
        self._summary = summary or ProdOpsSummary(resource_group="rg-lunaris-prod", currency="CAD")

    async def get_summary(self) -> ProdOpsSummary:
        return self._summary

    async def get_cost_daily(self, days: int) -> CostSeries:
        # Oldest-first; a small deterministic ramp so the chart has shape. The last day (the anchor)
        # is partial — the real Cost Management feed lags ~8-24h.
        points = tuple(
            CostPoint(
                day=_ANCHOR - timedelta(days=offset),
                amount=round(2.0 + (days - 1 - offset) % 5 * 0.5, 2),
                partial=offset == 0,
            )
            for offset in range(days - 1, -1, -1)
        )
        return CostSeries(points=points, currency=self._summary.currency)

    async def get_compute_series(self, days: int) -> ComputeSeries:
        # Hourly, oldest-first. A deterministic diurnal-ish wave so usage and cost have shape: the
        # worker "wakes" for a few hours each day (more replicas/CPU → more cost).
        anchor = datetime.combine(_ANCHOR, time(0))
        hours = days * 24
        points = tuple(
            ComputePoint(
                hour=anchor - timedelta(hours=offset),
                replicas=float((offset % 8 == 0) + 1),
                cpu_cores=round(0.5 + (offset % 8 == 0) * 1.5, 2),
                memory_gb=round(1.0 + (offset % 8 == 0) * 3.0, 2),
                cost=round(0.05 + (offset % 8 == 0) * 0.20, 3),
            )
            for offset in range(hours - 1, -1, -1)
        )
        return ComputeSeries(points=points, currency=self._summary.currency)
