from typing import Protocol

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
