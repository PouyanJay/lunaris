import asyncio
import base64
import os
from datetime import UTC, datetime

from .credential_store_protocol import BYOK_PROVIDERS, CredentialStatus
from .crypto import EncryptedSecret

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "provider_credentials"
_PK = "user_id,provider"


class SupabaseCredentialStore:
    """The production BYOK credential store: Supabase Postgres, lazy service-role client.

    Mirrors the runtime Supabase stores — the service-role client bypasses RLS (the
    ``provider_credentials`` table is RLS-enabled with NO policies, so it is reachable only by the
    backend, never by a user-JWT or anon client), and is built lazily on first use, so construction
    needs no creds and no network. The synchronous supabase-py calls run off the event loop via
    ``asyncio.to_thread``.

    The encrypted blob is stored as base64 ``text`` (``ciphertext`` + ``nonce``) rather than
    ``bytea`` — the values are opaque AEAD output either way, and base64 text sidesteps PostgREST's
    bytea hex-encoding round-trip. ``last4`` is the only plaintext-derived field stored, for masked
    status display without decrypting; the key itself is never persisted in the clear.
    """

    def __init__(
        self,
        *,
        url_env: str = _URL_ENV,
        service_key_env: str = _SERVICE_KEY_ENV,
        client: object | None = None,
    ) -> None:
        self._url_env = url_env
        self._service_key_env = service_key_env
        # An injected client (tests) skips lazy construction; production leaves it None so the
        # service-role client is built from the environment on first use.
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot store credentials"
                )
            self._client = create_client(url, key)
        return self._client

    async def set(
        self, *, user_id: str, provider: str, secret: EncryptedSecret, last4: str | None
    ) -> None:
        client = self._ensure_client()
        row = {
            "user_id": user_id,
            "provider": provider,
            "ciphertext": base64.b64encode(secret.ciphertext).decode(),
            "nonce": base64.b64encode(secret.nonce).decode(),
            "last4": last4,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        # Upsert on the composite PK so re-setting a provider rotates the key in place.
        await asyncio.to_thread(
            lambda: client.table(_TABLE).upsert(row, on_conflict=_PK).execute()  # type: ignore[attr-defined]
        )

    async def get(self, *, user_id: str, provider: str) -> EncryptedSecret | None:
        client = self._ensure_client()
        response = await asyncio.to_thread(
            lambda: (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("ciphertext, nonce")
                .eq("user_id", user_id)
                .eq("provider", provider)
                .limit(1)
                .execute()
            )
        )
        rows = response.data or []
        if not rows:
            return None
        row = rows[0]
        return EncryptedSecret(
            nonce=base64.b64decode(str(row["nonce"])),
            ciphertext=base64.b64decode(str(row["ciphertext"])),
        )

    async def statuses(self, *, user_id: str) -> list[CredentialStatus]:
        client = self._ensure_client()
        response = await asyncio.to_thread(
            lambda: (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("provider, last4")
                .eq("user_id", user_id)
                .execute()
            )
        )
        rows = response.data or []
        # "Set" is whether the user has a row for the provider — independent of last4 (a <4-char key
        # stores last4 as null, yet the credential is set). Keep the two concepts separate so a
        # null-last4 row never reads as unset.
        set_providers = {str(row["provider"]) for row in rows}
        last4_by_provider = {
            str(row["provider"]): (str(row["last4"]) if row.get("last4") else None) for row in rows
        }
        return [
            CredentialStatus(
                provider=provider,
                is_set=provider in set_providers,
                last4=last4_by_provider.get(provider),
            )
            for provider in BYOK_PROVIDERS
        ]

    async def delete(self, *, user_id: str, provider: str) -> bool:
        client = self._ensure_client()
        # Ask PostgREST for an exact count so "did anything get deleted?" doesn't depend on the
        # client's implicit return-representation default. Mirrors the runtime Supabase stores.
        response = await asyncio.to_thread(
            lambda: (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .delete(count="exact")
                .eq("user_id", user_id)
                .eq("provider", provider)
                .execute()
            )
        )
        return (response.count or 0) > 0
