from .base import CamelModel


class CredentialStatusView(CamelModel):
    """What the BYOK API reveals about one provider key — set/unset + last4, never the value."""

    provider: str
    is_set: bool
    last4: str | None


class CredentialTestResult(CamelModel):
    """The result of probing a key without storing it: whether the provider accepted it, plus a
    value-free detail when it didn't (for the Settings "Test" button)."""

    ok: bool
    detail: str | None = None
