from typing import Protocol

from .compute import ComputeSeries
from .cost import CostSeries
from .power import PowerState
from .summary import ProdOpsSummary


class IProdOpsProvider(Protocol):
    """The boundary the prod-operations admin surface reads Azure through.

    One implementation talks to Azure ARM (cost-management + monitor + container-apps) via the API's
    managed identity; the in-memory fake returns deterministic data for tests and the no-Azure path.
    Keeping it a Protocol lets the router stay identical whether or not Azure is reachable.
    """

    async def get_summary(self) -> ProdOpsSummary:
        """The overview the dashboard opens on (covered resource group + billing currency)."""
        ...

    async def get_cost_daily(self, days: int) -> CostSeries:
        """Daily Azure spend for the covered resource group over the last ``days`` days (the most
        recent day flagged ``partial`` — cost data lags ~8-24h)."""
        ...

    async def get_compute_series(self, days: int) -> ComputeSeries:
        """Hourly prod compute over the last ``days`` days: usage (replicas + CPU + memory) plus the
        amortized hourly cost, for the dual-axis chart."""
        ...

    async def get_power_state(self) -> PowerState:
        """Whether production is on, plus each governed app's run state."""
        ...

    async def set_power(self, *, on: bool) -> PowerState:
        """Start (``on=True``) or stop (``on=False``) the prod apps, returning the new state.
        Stopping zeroes the always-on cost; only the fixed registry floor remains."""
        ...
