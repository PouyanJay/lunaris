"""Tests for the ElevenLabs probe validator (V3 voice BYOK) — the set-time key check.

The network call is injected, so the decision logic (reject a 401, accept a 2xx/429, surface an
un-verifiable outcome) is exercised offline. The composite is checked too: each probe must no-op
for a name that is not its own, so composing Anthropic + ElevenLabs covers both with one validator.
"""

import pytest
from lunaris_api.secrets import (
    CompositeSecretValidator,
    ElevenLabsProbeValidator,
    SecretValidationError,
)
from lunaris_api.secrets.validator import ElevenLabsProbe


def _probe_returning(status_code: int) -> ElevenLabsProbe:
    async def probe(value: str) -> int:
        return status_code

    return probe


async def test_a_valid_key_passes() -> None:
    # Act / Assert — a 200 from the authenticated endpoint proves the key is real.
    await ElevenLabsProbeValidator(probe=_probe_returning(200)).validate("elevenlabs", "sk_good")


async def test_a_rate_limited_key_still_passes() -> None:
    # 429 means authenticated-but-throttled — the key is valid, do not reject it.
    await ElevenLabsProbeValidator(probe=_probe_returning(429)).validate("elevenlabs", "sk_good")


async def test_a_rejected_key_raises() -> None:
    with pytest.raises(SecretValidationError, match="rejected"):
        await ElevenLabsProbeValidator(probe=_probe_returning(401)).validate("elevenlabs", "sk_bad")


async def test_an_unreachable_provider_is_unverifiable() -> None:
    async def failing_probe(value: str) -> int:
        raise TimeoutError("no route")

    with pytest.raises(SecretValidationError, match="Could not reach ElevenLabs"):
        await ElevenLabsProbeValidator(probe=failing_probe).validate("elevenlabs", "sk_any")


async def test_a_non_elevenlabs_name_is_a_noop() -> None:
    # The probe would reject, but the validator must not touch a key that is not its own.
    await ElevenLabsProbeValidator(probe=_probe_returning(401)).validate("anthropic", "sk-ant")


async def test_composite_passes_through_a_foreign_provider_name() -> None:
    # Arrange — an ElevenLabs probe that would reject; an Anthropic-name key must skip it entirely.
    composite = CompositeSecretValidator([ElevenLabsProbeValidator(probe=_probe_returning(401))])

    # Act / Assert — the foreign name is untouched (no raise).
    await composite.validate("anthropic", "sk-ant")


async def test_composite_rejects_a_bad_key_for_its_own_provider() -> None:
    # Arrange
    composite = CompositeSecretValidator([ElevenLabsProbeValidator(probe=_probe_returning(401))])

    # Act / Assert — the elevenlabs name routes to the rejecting probe.
    with pytest.raises(SecretValidationError):
        await composite.validate("elevenlabs", "sk_bad")
