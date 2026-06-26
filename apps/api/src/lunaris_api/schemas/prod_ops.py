from datetime import date

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
