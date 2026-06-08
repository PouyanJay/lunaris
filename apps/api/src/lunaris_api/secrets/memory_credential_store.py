from .credential_store_protocol import BYOK_PROVIDERS, CredentialStatus
from .crypto import EncryptedSecret


class InMemoryCredentialStore:
    """In-process BYOK credential store — the no-key/CI fallback and test stub.

    Keys live only for the process lifetime (lost on restart); durable, cross-machine storage
    requires the Supabase-backed store. Entries are keyed by ``(user_id, provider)`` so isolation is
    structural — a read/delete for one user can never reach another's row. Stores the encrypted blob
    + the plaintext's last4 (for masked status); the plaintext itself never enters this store.
    """

    def __init__(self) -> None:
        self._secrets: dict[tuple[str, str], EncryptedSecret] = {}
        self._last4: dict[tuple[str, str], str | None] = {}

    async def set(
        self, *, user_id: str, provider: str, secret: EncryptedSecret, last4: str | None
    ) -> None:
        self._secrets[(user_id, provider)] = secret
        self._last4[(user_id, provider)] = last4

    async def get(self, *, user_id: str, provider: str) -> EncryptedSecret | None:
        return self._secrets.get((user_id, provider))

    async def statuses(self, *, user_id: str) -> list[CredentialStatus]:
        return [
            CredentialStatus(
                provider=provider,
                is_set=(user_id, provider) in self._secrets,
                last4=self._last4.get((user_id, provider)),
            )
            for provider in BYOK_PROVIDERS
        ]

    async def delete(self, *, user_id: str, provider: str) -> bool:
        """Drop a user's credential. Idempotent: returns False if it wasn't set."""
        key = (user_id, provider)
        if key not in self._secrets:
            return False
        del self._secrets[key]
        self._last4.pop(key, None)
        return True
