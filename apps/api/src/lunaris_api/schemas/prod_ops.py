from datetime import date, datetime

from .base import CamelModel


class ProdOpsSummaryView(CamelModel):
    """The prod-operations overview the admin dashboard opens on: the Azure resource group the
    figures cover and the billing currency they are reported in."""

    resource_group: str
    currency: str


class CostPointView(CamelModel):
    """One day's Azure spend. ``is_partial`` marks the most recent day, whose figure is still
    settling (Cost Management lags ~8-24h) and must not be read as a drop."""

    day: date
    amount: float
    is_partial: bool


class CostSeriesView(CamelModel):
    """Daily Azure spend for the prod cost chart: points oldest-first + the billing currency."""

    currency: str
    points: list[CostPointView]


class ComputePointView(CamelModel):
    """One hour of prod compute: usage (active replicas + CPU cores + memory GB) and that hour's
    amortized cost — the dual-axis chart plots a usage metric against cost."""

    hour: datetime
    replicas: float
    cpu_cores: float
    memory_gb: float
    cost: float


class ComputeSeriesView(CamelModel):
    """Hourly prod compute for the dual-axis chart: points oldest-first + the billing currency."""

    currency: str
    points: list[ComputePointView]
