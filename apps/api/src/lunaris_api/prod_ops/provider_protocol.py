from typing import Protocol

from .cost import CostSeries
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
