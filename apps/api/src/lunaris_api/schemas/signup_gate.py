from datetime import datetime

from .base import CamelModel


class SignupGateView(CamelModel):
    """The admin view of the signup gate: the plaintext shared code (admins only), whether it is
    enforced, and when it last changed. Reachable only behind the admin allowlist."""

    invite_code: str
    enforced: bool
    updated_at: datetime | None


class SignupGateStatusView(CamelModel):
    """The public, pre-login status of the gate — whether an invite code is required. Carries no
    code, so the sign-up screen can show/hide the invite field without leaking the secret."""

    enforced: bool


class SignupGateUpdate(CamelModel):
    """An admin change to the gate. Either field may be omitted to leave it unchanged: rotate the
    code (``inviteCode``), open/close the gate (``enforced``), or both."""

    invite_code: str | None = None
    enforced: bool | None = None
