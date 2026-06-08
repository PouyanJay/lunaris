from .base import CamelModel


class MeResponse(CamelModel):
    """The authenticated caller's identity."""

    user_id: str
