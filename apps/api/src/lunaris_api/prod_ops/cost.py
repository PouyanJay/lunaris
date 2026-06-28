from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CostPoint:
    """One day's Azure spend for the covered resource group.

    ``partial`` marks a day whose figure is still settling — Azure Cost Management lags ~8-24h, so
    the most recent day is always incomplete and must be shown as such rather than read as a drop.
    """

    day: date
    amount: float
    partial: bool


@dataclass(frozen=True)
class CostSeries:
    """A daily Azure-spend series for the prod cost chart: the points oldest-first + their currency.

    Tightly coupled to ``CostPoint`` (its only element type), so they share a module.
    """

    points: tuple[CostPoint, ...]
    currency: str
