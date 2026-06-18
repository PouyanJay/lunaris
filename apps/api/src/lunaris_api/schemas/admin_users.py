from datetime import datetime

from .base import CamelModel


class AdminAccountView(CamelModel):
    """One account on the admin user-management list: identity + status, plus whether it is an admin
    (email on the allowlist) and whether it is the requesting admin's own account (which can't be
    deleted)."""

    id: str
    email: str | None
    created_at: datetime | None
    last_sign_in_at: datetime | None
    email_confirmed: bool
    is_admin: bool
    is_self: bool
