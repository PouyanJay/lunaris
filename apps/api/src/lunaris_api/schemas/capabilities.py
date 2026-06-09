from .base import CamelModel


class CapabilityStatusView(CamelModel):
    """One capability's active provider on the wire: live (keyed) or its keyless fallback."""

    capability: str
    mode: str
    provider: str
