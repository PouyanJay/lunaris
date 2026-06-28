from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ComputePoint:
    """One hour of prod compute: how much ran (active replicas + CPU cores + memory) and what that
    hour cost. The dual-axis chart overlays a usage metric (bars) against ``cost`` (line)."""

    hour: datetime
    replicas: float
    cpu_cores: float
    memory_gb: float
    cost: float


@dataclass(frozen=True)
class ComputeSeries:
    """An hourly prod-compute series for the dual-axis chart: points oldest-first + their currency.

    Tightly coupled to ``ComputePoint`` (its only element type), so they share a module.
    """

    points: tuple[ComputePoint, ...]
    currency: str
