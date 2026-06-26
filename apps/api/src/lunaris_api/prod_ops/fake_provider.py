from .summary import ProdOpsSummary


class FakeProdOpsProvider:
    """A deterministic ``IProdOpsProvider`` for tests and the no-Azure path.

    Returns the summary it was seeded with — no Azure calls — so the router, admin gate, and web
    section can be exercised hermetically. The default summary covers ``rg-lunaris-prod`` in CAD,
    matching the live environment the real adapter reports on.
    """

    def __init__(self, summary: ProdOpsSummary | None = None) -> None:
        self._summary = summary or ProdOpsSummary(resource_group="rg-lunaris-prod", currency="CAD")

    async def get_summary(self) -> ProdOpsSummary:
        return self._summary
