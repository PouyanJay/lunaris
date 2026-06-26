from .base import CamelModel


class ProdOpsSummaryView(CamelModel):
    """The prod-operations overview the admin dashboard opens on: the Azure resource group the
    figures cover and the billing currency they are reported in."""

    resource_group: str
    currency: str
