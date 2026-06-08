import base64
import binascii
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# The base64-encoded AES master key, injected from the secret manager (Key Vault) as an env var —
# never the .env, never the DB. Absent ⇒ BYOK is disabled (the cipher factory returns None).
MASTER_KEY_ENV = "LUNARIS_KEY_ENC_MASTER"

_NONCE_BYTES = 12  # the standard 96-bit GCM nonce
_VALID_KEY_LENGTHS = (16, 24, 32)  # AES-128 / AES-192 / AES-256


class CryptoError(Exception):
    """Base for at-rest-encryption errors."""


class MasterKeyUnavailableError(CryptoError):
    """The master key is missing or malformed — a deployment/config error, not a client one."""


class DecryptionError(CryptoError):
    """A ciphertext failed authenticated decryption — tampered, wrong key, or wrong AAD."""


@dataclass(frozen=True)
class EncryptedSecret:
    """An AES-GCM ciphertext + its nonce — the at-rest form of a provider key. Opaque: it carries
    no plaintext and is safe to persist. The GCM auth tag is appended to ``ciphertext`` by the
    library, so these two fields are everything decryption needs (plus the matching AAD)."""

    nonce: bytes
    ciphertext: bytes


class SecretCipher:
    """AES-256-GCM authenticated encryption for per-user provider keys, at rest.

    Each ``encrypt`` draws a fresh random nonce (so identical plaintexts never yield identical
    ciphertexts) and binds the value to an ``aad`` string — the caller passes
    ``"<user_id>:<provider>"`` so a ciphertext lifted from one row cannot be decrypted under a
    different user or provider; GCM authenticates the AAD, so a mismatch fails closed. Any tamper,
    wrong master key, or wrong AAD raises ``DecryptionError`` rather than returning corrupt bytes.
    The plaintext key is never logged.
    """

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) not in _VALID_KEY_LENGTHS:
            raise MasterKeyUnavailableError(
                f"Master key must be {_VALID_KEY_LENGTHS} bytes; got {len(master_key)}."
            )
        self._aesgcm = AESGCM(master_key)

    def encrypt(self, plaintext: str, *, aad: str) -> EncryptedSecret:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
        return EncryptedSecret(nonce=nonce, ciphertext=ciphertext)

    def decrypt(self, secret: EncryptedSecret, *, aad: str) -> str:
        try:
            plaintext = self._aesgcm.decrypt(secret.nonce, secret.ciphertext, aad.encode("utf-8"))
        except InvalidTag as exc:
            # Don't leak which of tamper / wrong-key / wrong-AAD it was.
            raise DecryptionError("Could not decrypt the stored secret.") from exc
        return plaintext.decode("utf-8")


def build_secret_cipher(master_key_b64: str | None) -> SecretCipher | None:
    """Build the cipher from a base64 master key, or ``None`` when unconfigured (BYOK disabled).

    A present-but-malformed key is a loud ``MasterKeyUnavailableError`` (a deployment mistake we
    must not silently ignore), distinct from an absent key (``None`` → the feature is simply off).
    """
    if not master_key_b64:
        return None
    try:
        key = base64.b64decode(master_key_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MasterKeyUnavailableError(f"{MASTER_KEY_ENV} is not valid base64.") from exc
    return SecretCipher(key)
