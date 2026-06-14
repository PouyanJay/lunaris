"""Tests for the ElevenLabs probe validator (V3 voice BYOK) — the set-time key check.

The network call is injected, so the decision logic runs offline: accept a 2xx/429, reject the
genuine bad-key 401s, but ACCEPT a 401 that means "valid key, just lacks the /v1/user permission"
(a scoped key can still narrate), and surface any other outcome as un-verifiable. The composite is
checked too: each probe must no-op for a name that is not its own.
"""

import pytest
from lunaris_api.secrets import (
    CompositeSecretValidator,
    ElevenLabsProbeValidator,
    SecretValidationError,
)
from lunaris_api.secrets.validator import ElevenLabsProbe


def _probe_returning(status_code: int, detail_status: str = "") -> ElevenLabsProbe:
    async def probe(value: str) -> tuple[int, str]:
        return status_code, detail_status

    return probe


async def test_a_valid_key_passes() -> None:
    # Act / Assert — a 200 from the authenticated endpoint proves the key is real.
    await ElevenLabsProbeValidator(probe=_probe_returning(200)).validate("elevenlabs", "sk_good")


async def test_a_rate_limited_key_still_passes() -> None:
    # 429 means authenticated-but-throttled — the key is valid, do not reject it.
    await ElevenLabsProbeValidator(probe=_probe_returning(429)).validate("elevenlabs", "sk_good")


async def test_an_invalid_key_raises() -> None:
    # 401 invalid_api_key is the genuine bad-key signal → reject.
    probe = _probe_returning(401, "invalid_api_key")
    with pytest.raises(SecretValidationError, match="rejected"):
        await ElevenLabsProbeValidator(probe=probe).validate("elevenlabs", "sk_bad")


async def test_a_scoped_key_lacking_the_user_permission_passes() -> None:
    # The regression: a VALID key that can synthesise speech but lacks the /v1/user permission
    # authenticates and returns 401 missing_permissions — it must be accepted, not rejected.
    probe = _probe_returning(401, "missing_permissions")
    await ElevenLabsProbeValidator(probe=probe).validate("elevenlabs", "sk_scoped")


async def test_a_needs_authorization_status_raises() -> None:
    # needs_authorization is ElevenLabs' "no api key / auth header received" signal (confirmed live)
    # — a genuine bad-credentials case, so it stays in the reject set alongside invalid_api_key.
    probe = _probe_returning(401, "needs_authorization")
    with pytest.raises(SecretValidationError, match="rejected"):
        await ElevenLabsProbeValidator(probe=probe).validate("elevenlabs", "sk_bad")


async def test_a_401_with_an_unparseable_body_is_accepted() -> None:
    # A 401 whose body we can't parse (detail_status == "") isn't a known bad-key signal, so the
    # key is treated as authenticated-but-scoped and accepted (degrade-to-silent, never block it).
    probe = _probe_returning(401, "")
    await ElevenLabsProbeValidator(probe=probe).validate("elevenlabs", "sk_scoped")


async def test_an_unreachable_provider_is_unverifiable() -> None:
    async def failing_probe(value: str) -> tuple[int, str]:
        raise TimeoutError("no route")

    with pytest.raises(SecretValidationError, match="Could not reach ElevenLabs"):
        await ElevenLabsProbeValidator(probe=failing_probe).validate("elevenlabs", "sk_any")


async def test_an_unexpected_status_is_unverifiable() -> None:
    # A 500 (or anything that isn't authenticated or a 401) is surfaced, not silently accepted.
    probe = _probe_returning(500)
    with pytest.raises(SecretValidationError, match="Could not verify"):
        await ElevenLabsProbeValidator(probe=probe).validate("elevenlabs", "sk_any")


async def test_a_non_elevenlabs_name_is_a_noop() -> None:
    # The probe would reject, but the validator must not touch a key that is not its own.
    probe = _probe_returning(401, "invalid_api_key")
    await ElevenLabsProbeValidator(probe=probe).validate("anthropic", "sk-ant")


async def test_composite_passes_through_a_foreign_provider_name() -> None:
    # Arrange — an ElevenLabs probe that would reject; an Anthropic-name key must skip it entirely.
    probe = _probe_returning(401, "invalid_api_key")
    composite = CompositeSecretValidator([ElevenLabsProbeValidator(probe=probe)])

    # Act / Assert — the foreign name is untouched (no raise).
    await composite.validate("anthropic", "sk-ant")


async def test_composite_rejects_a_bad_key_for_its_own_provider() -> None:
    # Arrange
    probe = _probe_returning(401, "invalid_api_key")
    composite = CompositeSecretValidator([ElevenLabsProbeValidator(probe=probe)])

    # Act / Assert — the elevenlabs name routes to the rejecting probe.
    with pytest.raises(SecretValidationError):
        await composite.validate("elevenlabs", "sk_bad")
