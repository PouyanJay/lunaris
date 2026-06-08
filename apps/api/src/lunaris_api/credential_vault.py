from .secrets import (
    BYOK_PROVIDERS,
    CredentialStatus,
    ICredentialStore,
    ISecretValidator,
    SecretCipher,
    contains_control_characters,
)


class UnknownProviderError(Exception):
    """A provider outside ``BYOK_PROVIDERS`` was given — the router maps this to a 404."""


class CredentialVault:
    """Application service for per-user BYOK provider keys — the one door the API uses.

    Composes the three primitives: the ``SecretCipher`` (encrypt at rest), the ``ICredentialStore``
    (persist ciphertext, scoped per user), and an ``ISecretValidator`` (probe a key's validity). Set
    encrypts + stores; ``reveal`` decrypts for backend-internal use (per-run key injection at build
    time) and is NEVER wired to a route; ``statuses`` returns the masked set/unset surface; ``test``
    probes a key without storing it. Every operation is scoped to an authenticated ``user_id``, and
    the blob is bound to ``"<user_id>:<provider>"`` as AAD so it can't be reused on another row.
    """

    def __init__(
        self,
        *,
        store: ICredentialStore,
        cipher: SecretCipher,
        validator: ISecretValidator,
    ) -> None:
        self._store = store
        self._cipher = cipher
        self._validator = validator

    async def set(self, *, user_id: str, provider: str, value: str) -> CredentialStatus:
        """Validate, probe, encrypt, and store a provider key (upsert = rotate). Returns the masked
        status. Raises ``UnknownProviderError`` for an unrecognised provider, ``ValueError`` for a
        malformed value, or ``SecretValidationError`` if the provider probe rejects the key. A
        rejected key is never stored."""
        self._require_known(provider)
        self._require_valid_value(value)
        # Probe before persisting, so a rejected key is never stored (parity with the file store).
        await self._validator.validate(provider, value)
        secret = self._cipher.encrypt(value, aad=self._aad(user_id, provider))
        last4 = value[-4:] if len(value) >= 4 else None
        await self._store.set(user_id=user_id, provider=provider, secret=secret, last4=last4)
        return CredentialStatus(provider=provider, is_set=True, last4=last4)

    async def reveal(self, *, user_id: str, provider: str) -> str | None:
        """Backend-internal: decrypt the stored key for per-run injection at build time. NEVER wire
        to a route. Returns ``None`` when the user has no key for that provider."""
        secret = await self._store.get(user_id=user_id, provider=provider)
        if secret is None:
            return None
        return self._cipher.decrypt(secret, aad=self._aad(user_id, provider))

    async def statuses(self, *, user_id: str) -> list[CredentialStatus]:
        return await self._store.statuses(user_id=user_id)

    async def delete(self, *, user_id: str, provider: str) -> bool:
        """Remove a provider key. Idempotent (False if absent). Raises ``UnknownProviderError``."""
        self._require_known(provider)
        return await self._store.delete(user_id=user_id, provider=provider)

    async def test(self, *, provider: str, value: str) -> None:
        """Probe a key's validity WITHOUT storing it. Raises ``UnknownProviderError`` /
        ``ValueError`` for a malformed request, or ``SecretValidationError`` if the provider rejects
        the key."""
        self._require_known(provider)
        self._require_valid_value(value)
        await self._validator.validate(provider, value)

    @staticmethod
    def _aad(user_id: str, provider: str) -> str:
        return f"{user_id}:{provider}"

    @staticmethod
    def _require_known(provider: str) -> None:
        if provider not in BYOK_PROVIDERS:
            raise UnknownProviderError(provider)

    @staticmethod
    def _require_valid_value(value: str) -> None:
        # Non-empty + no control characters (the value is never echoed in the error → can't leak).
        if not value or contains_control_characters(value):
            raise ValueError("Key value must be non-empty and free of control characters.")
