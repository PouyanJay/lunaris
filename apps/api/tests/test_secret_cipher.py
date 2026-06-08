"""Tests for the BYOK at-rest cipher (Phase 2, T4) — AES-256-GCM authenticated encryption for
per-user provider keys, with the plaintext bound to a per-row AAD so a ciphertext can't be replayed
under a different user/provider.

Deterministic + offline: the master key is a fixed 32 zero-bytes here; the nonce is random per
encrypt (proven below), so round-trip is the contract, not byte-equality of ciphertext.
"""

import base64

import pytest
from lunaris_api.secrets import (
    DecryptionError,
    EncryptedSecret,
    MasterKeyUnavailableError,
    SecretCipher,
    build_secret_cipher,
)

_MASTER_KEY = bytes(32)  # 32 zero-bytes — a valid AES-256 key for deterministic tests
_MASTER_KEY_B64 = base64.b64encode(_MASTER_KEY).decode()


def _cipher() -> SecretCipher:
    return SecretCipher(_MASTER_KEY)


def test_encrypt_then_decrypt_round_trips() -> None:
    # Arrange
    cipher = _cipher()
    plaintext = "sk-ant-super-secret-value"

    # Act
    enc = cipher.encrypt(plaintext, aad="user-1:anthropic")
    recovered = cipher.decrypt(enc, aad="user-1:anthropic")

    # Assert
    assert recovered == plaintext


def test_ciphertext_never_contains_the_plaintext() -> None:
    # Arrange
    cipher = _cipher()

    # Act
    enc = cipher.encrypt("plaintext-key", aad="u:anthropic")

    # Assert — at rest, neither the ciphertext nor the nonce reveal the value.
    assert b"plaintext-key" not in enc.ciphertext
    assert b"plaintext-key" not in enc.nonce


def test_each_encrypt_uses_a_fresh_96_bit_nonce() -> None:
    # Arrange
    cipher = _cipher()

    # Act — the same plaintext + AAD encrypted several times.
    results = [cipher.encrypt("same", aad="u:anthropic") for _ in range(5)]

    # Assert — every nonce is a fresh 96-bit value (so identical plaintexts never collide), which
    # makes every ciphertext distinct too (no deterministic-encryption leak).
    nonces = {enc.nonce for enc in results}
    assert len(nonces) == len(results)
    assert all(len(enc.nonce) == 12 for enc in results)
    assert len({enc.ciphertext for enc in results}) == len(results)


def test_decrypt_rejects_a_tampered_ciphertext() -> None:
    # Arrange
    cipher = _cipher()
    enc = cipher.encrypt("secret", aad="u:anthropic")
    tampered = EncryptedSecret(
        nonce=enc.nonce, ciphertext=enc.ciphertext[:-1] + bytes([enc.ciphertext[-1] ^ 0x01])
    )

    # Act / Assert — GCM's auth tag catches the flip.
    with pytest.raises(DecryptionError):
        cipher.decrypt(tampered, aad="u:anthropic")


def test_decrypt_rejects_a_mismatched_aad() -> None:
    # Arrange — encrypt bound to one (user, provider); decrypt with another.
    cipher = _cipher()
    enc = cipher.encrypt("secret", aad="user-1:anthropic")

    # Act / Assert — moving a ciphertext to a different row/user fails (AAD is authenticated).
    with pytest.raises(DecryptionError):
        cipher.decrypt(enc, aad="user-2:anthropic")


def test_decrypt_rejects_a_different_master_key() -> None:
    # Arrange — encrypt under one key, decrypt under another.
    enc = SecretCipher(bytes(32)).encrypt("secret", aad="u:anthropic")
    other = SecretCipher(bytes([1]) + bytes(31))

    # Act / Assert
    with pytest.raises(DecryptionError):
        other.decrypt(enc, aad="u:anthropic")


def test_rejects_a_wrong_length_master_key() -> None:
    # Act / Assert — AES keys are 16/24/32 bytes; anything else is a config error.
    with pytest.raises(MasterKeyUnavailableError):
        SecretCipher(bytes(20))


def test_build_from_env_value_round_trips() -> None:
    # Arrange / Act — the production seam: a base64 key string → a working cipher.
    cipher = build_secret_cipher(_MASTER_KEY_B64)

    # Assert
    assert cipher is not None
    enc = cipher.encrypt("k", aad="u:search")
    assert cipher.decrypt(enc, aad="u:search") == "k"


def test_build_returns_none_when_unconfigured() -> None:
    # Act / Assert — no master key ⇒ no cipher (BYOK disabled), not a crash.
    assert build_secret_cipher(None) is None
    assert build_secret_cipher("") is None


def test_build_rejects_an_invalid_base64_key() -> None:
    # Act / Assert — a malformed master key is a loud deployment error, never a silent skip.
    with pytest.raises(MasterKeyUnavailableError):
        build_secret_cipher("not-valid-base64!!!")
