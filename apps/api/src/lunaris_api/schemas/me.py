from .base import CamelModel


class MeResponse(CamelModel):
    """The authenticated caller's identity, plus whether they may manage the signup invite-gate."""

    user_id: str
    # On the admin allowlist (LUNARIS_ADMIN_EMAILS). The web shows the Invitations admin screen only
    # when true; the API still enforces admin access on every admin endpoint regardless.
    is_admin: bool
