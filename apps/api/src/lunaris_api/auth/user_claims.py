from dataclasses import dataclass


@dataclass(frozen=True)
class UserClaims:
    """The verified identity a token carries: the subject (``sub``) and the email claim.

    ``email`` is optional — it backs the admin allowlist (``Settings.is_admin``), but Supabase only
    populates it for email-based identities, so a token without one is a non-admin, not an error.
    """

    user_id: str
    email: str | None
