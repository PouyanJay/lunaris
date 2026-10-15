from datetime import date, datetime

from ..prod_ops import PowerStatus, ResourceKind
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


class ResourcePowerView(CamelModel):
    """One governed prod resource's run state. ``status`` is ``transitioning`` while Azure is still
    starting or stopping it; ``running`` is the plain on/off reading of the same state."""

    name: str
    kind: ResourceKind
    status: PowerStatus
    running: bool


class PowerStateView(CamelModel):
    """Whether production is on, plus the run state of each resource the on/off switch governs.
    ``settled`` is false while any resource is mid-transition (poll until it turns true)."""

    is_on: bool
    settled: bool
    resources: list[ResourcePowerView]


class PowerToggleRequest(CamelModel):
    """Start (``on=True``) or stop (``on=False``) production. ``confirm`` MUST be true — stopping
    prod is a self-inflicted outage, so the switch requires an explicit, deliberate confirmation."""

    on: bool
    confirm: bool
