from dataclasses import dataclass
from typing import Protocol

from .crypto import EncryptedSecret

# The per-user keys a tenant brings (BYOK) — the LLM/search/video keys a build needs, NOT the
# platform infra (Supabase) or observability (LangSmith) keys, which stay operator-owned. Must stay
# in lockstep with the ``provider`` CHECK in the provider_credentials migration: a new provider is a
# change in both places.
BYOK_PROVIDERS: tuple[str, ...] = ("anthropic", "voyage", "search", "youtube")


@dataclass(frozen=True)
class CredentialStatus:
    """The only thing ever revealed about a stored credential — never the value, only its last4."""

    provider: str
    is_set: bool
    last4: str | None


class ICredentialStore(Protocol):
    """Per-user storage for BYOK provider keys — encrypted blobs only, never plaintext.

    The store persists the ``EncryptedSecret`` the ``SecretCipher`` produced and returns it for
    decryption at use time; it never sees or returns a plaintext key. Every method is scoped to a
    ``user_id`` (the authenticated owner), so one tenant can neither read nor delete another's keys.
    Concrete backends: an in-memory fallback (no-key/CI) and the Supabase-backed store (production,
    RLS-enabled + server-only via the service-role client).

    Contract: ``set`` upserts (one credential per provider per user — re-setting rotates it);
    ``get`` returns ``None`` when the user has no key for that provider; ``statuses`` lists every
    ``BYOK_PROVIDERS`` entry with its set/unset state (+ last4); ``delete`` is idempotent (``True``
    if a row was removed, ``False`` if absent or not the caller's).
    """

    async def set(
        self, *, user_id: str, provider: str, secret: EncryptedSecret, last4: str | None
    ) -> None: ...

    async def get(self, *, user_id: str, provider: str) -> EncryptedSecret | None: ...

    async def statuses(self, *, user_id: str) -> list[CredentialStatus]: ...

    async def delete(self, *, user_id: str, provider: str) -> bool: ...
