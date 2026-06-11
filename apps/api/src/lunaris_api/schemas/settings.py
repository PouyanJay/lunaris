from pydantic import BaseModel, SecretStr

from .base import CamelModel


class SecretStatusView(CamelModel):
    """What the API reveals about one secret — set/unset + last 4 chars, never the value."""

    name: str
    is_set: bool
    last4: str | None


class SettingsView(CamelModel):
    """The settings surface: per-secret status + the current (read-only) pipeline mode."""

    secrets: list[SecretStatusView]
    pipeline: str
    # Whether the active pipeline can re-author a single lesson; the web hides the regenerate
    # action when False rather than offering a button the pipeline would reject with a 501.
    supports_lesson_regeneration: bool
    # Whether plain-language "Explain" can answer at all (hosted Claude OR the keyless server
    # tier); the web hides the affordance when False rather than offering a button that 503s.
    supports_explain: bool
    # Whether the HOSTED tier specifically (an Anthropic key) is reachable. The transcript's
    # dev-facing Explain stays hosted-only; the reader offers Explain on either tier.
    supports_hosted_explain: bool
    # Whether per-user BYOK is configured (a master key + Supabase). When True the web manages keys
    # through the authed per-user /api/credentials surface instead of this file-backed secret store.
    byok_enabled: bool
    # Whether runtime config is per-user (auth is configured). When True /api/config serves the
    # caller's own model selection (LangSmith is operator-only and absent from the surface); when
    # False it's the process-wide file store (single-user dev, incl. LangSmith).
    per_user_config_enabled: bool


class SecretValue(BaseModel):
    """Request body for setting a secret. ``SecretStr`` keeps the value out of logs/reprs.

    Note: control-char rejection is enforced in the router, not as a field validator here — a
    Pydantic 422 echoes the offending input back in its error body, which would leak the secret.
    """

    value: SecretStr
