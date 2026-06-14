"""Tests for the BYOK credential vault (Phase 2, T5) — the application service that composes the
cipher + store + validator into set / reveal / statuses / delete / test.

Deterministic + offline: a real ``SecretCipher`` over a fixed master key + the in-memory store +
an accepting validator (no network). The point is the orchestration — encrypt-on-set, decrypt-on-
reveal, AAD binding per (user, provider), value validation, and the probe path.
"""

import pytest
from _doubles import RejectingValidator
from lunaris_api.credential_vault import CredentialVault, UnknownProviderError
from lunaris_api.secrets import (
    AcceptingValidator,
    InMemoryCredentialStore,
    ISecretValidator,
    SecretCipher,
    SecretValidationError,
)

_MASTER_KEY = bytes(32)


def _vault(validator: ISecretValidator | None = None) -> CredentialVault:
    return CredentialVault(
        store=InMemoryCredentialStore(),
        cipher=SecretCipher(_MASTER_KEY),
        validator=validator or AcceptingValidator(),
    )


async def test_set_then_reveal_round_trips_the_plaintext() -> None:
    # Arrange
    vault = _vault()

    # Act — set encrypts at rest; reveal decrypts for backend use (per-run injection at build time).
    status = await vault.set(user_id="u-1", provider="anthropic", value="sk-ant-secret-key")
    revealed = await vault.reveal(user_id="u-1", provider="anthropic")

    # Assert — round-trips, and the masked status carries last4 (never the value).
    assert revealed == "sk-ant-secret-key"
    assert status.provider == "anthropic"
    assert status.is_set is True
    assert status.last4 == "-key"


async def test_reveal_is_bound_to_the_user_and_provider() -> None:
    # Arrange — A stores a key under one provider.
    store = InMemoryCredentialStore()
    vault = CredentialVault(
        store=store, cipher=SecretCipher(_MASTER_KEY), validator=AcceptingValidator()
    )
    await vault.set(user_id="u-a", provider="anthropic", value="a-key")

    # Act / Assert — another user reveals nothing (the row is theirs alone).
    assert await vault.reveal(user_id="u-b", provider="anthropic") is None


async def test_reveal_missing_is_none() -> None:
    assert await _vault().reveal(user_id="u-1", provider="search") is None


async def test_set_validates_the_key_with_the_provider_probe() -> None:
    # Arrange — a validator that rejects the key.
    vault = _vault(RejectingValidator())

    # Act / Assert — a rejected key is never stored.
    with pytest.raises(SecretValidationError):
        await vault.set(user_id="u-1", provider="anthropic", value="bad-key")
    assert await vault.reveal(user_id="u-1", provider="anthropic") is None


async def test_set_rejects_an_empty_or_control_char_value() -> None:
    vault = _vault()
    with pytest.raises(ValueError):
        await vault.set(user_id="u-1", provider="anthropic", value="")
    with pytest.raises(ValueError):
        await vault.set(user_id="u-1", provider="anthropic", value="line\nbreak")


async def test_set_rejects_an_unknown_provider() -> None:
    vault = _vault()
    with pytest.raises(UnknownProviderError):
        await vault.set(user_id="u-1", provider="openai", value="k")


async def test_statuses_lists_every_provider() -> None:
    # Arrange
    vault = _vault()
    await vault.set(user_id="u-1", provider="search", value="tvly-1234")

    # Act
    statuses = {s.provider: s for s in await vault.statuses(user_id="u-1")}

    # Assert — search is set with last4; the others report unset.
    assert statuses["search"].is_set is True
    assert statuses["search"].last4 == "1234"
    assert statuses["anthropic"].is_set is False


async def test_elevenlabs_is_a_supported_byok_provider() -> None:
    # ElevenLabs is the V3 voice key — the same vault, the same round-trip as the LLM/search keys.
    vault = _vault()

    # Act
    status = await vault.set(user_id="u-1", provider="elevenlabs", value="sk_eleven_secret")
    revealed = await vault.reveal(user_id="u-1", provider="elevenlabs")

    # Assert — round-trips, lists with the others, masks to last4.
    assert revealed == "sk_eleven_secret"
    assert status.provider == "elevenlabs"
    assert status.last4 == "cret"
    statuses = {s.provider: s for s in await vault.statuses(user_id="u-1")}
    assert statuses["elevenlabs"].is_set is True


async def test_delete_removes_a_key_and_is_owner_scoped() -> None:
    # Arrange
    vault = _vault()
    await vault.set(user_id="u-a", provider="anthropic", value="a-key")

    # Act / Assert — another user can't delete it; the owner can.
    assert await vault.delete(user_id="u-b", provider="anthropic") is False
    assert await vault.delete(user_id="u-a", provider="anthropic") is True
    assert await vault.reveal(user_id="u-a", provider="anthropic") is None


async def test_delete_rejects_an_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError):
        await _vault().delete(user_id="u-1", provider="openai")


async def test_test_probe_passes_for_a_good_key() -> None:
    # Act / Assert — the accepting validator raises nothing (does not store).
    await _vault().test(provider="anthropic", value="good-key")


async def test_test_probe_raises_for_a_bad_key() -> None:
    with pytest.raises(SecretValidationError):
        await _vault(RejectingValidator()).test(provider="anthropic", value="bad-key")


async def test_test_probe_rejects_an_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError):
        await _vault().test(provider="openai", value="k")


async def test_test_probe_rejects_an_empty_value() -> None:
    with pytest.raises(ValueError):
        await _vault().test(provider="anthropic", value="")
