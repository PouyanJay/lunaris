from dataclasses import dataclass


@dataclass(frozen=True)
class ProdOpsSummary:
    """The prod-operations overview the admin dashboard opens on: which Azure resource group the
    figures cover and the billing currency they are reported in.

    A read model surfaced by ``IProdOpsProvider``. The walking-skeleton shape — cost/compute series
    and power state hang off later provider methods, not this summary.
    """

    resource_group: str
    currency: str
