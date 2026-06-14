from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol


class SecretValidationError(Exception):
    """A provided secret failed validation (rejected, or could not be verified)."""


class ISecretValidator(Protocol):
    """Validates a secret before it is stored. Raises SecretValidationError to reject."""

    async def validate(self, name: str, value: str) -> None: ...


class AnthropicProbeValidator:
    """Validates the Anthropic key with a tiny live call; passes other secrets through.

    A 401 means a bad key → reject. A 429 means auth succeeded but we're rate-limited → accept
    (the key is valid). Any other transport failure is surfaced so the operator knows we
    couldn't verify it. The value is never logged.
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        self._model = model

    async def validate(self, name: str, value: str) -> None:
        if name != "anthropic":
            return
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=value)
        try:
            await client.messages.create(
                model=self._model,
                max_tokens=4,
                messages=[{"role": "user", "content": "ping"}],
            )
        except anthropic.AuthenticationError as exc:
            raise SecretValidationError("Anthropic rejected this API key.") from exc
        except anthropic.RateLimitError:
            return  # auth succeeded; being rate-limited proves the key is valid
        except Exception as exc:  # network, etc. — couldn't verify
            raise SecretValidationError(
                f"Could not reach Anthropic to verify the key ({type(exc).__name__})."
            ) from exc


# An injectable probe: takes the API key, returns (HTTP status code, the ElevenLabs error
# `detail.status` — "" when none), and raises on a transport failure (so the validator can tell
# "rejected" from "couldn't verify").
ElevenLabsProbe = Callable[[str], Awaitable[tuple[int, str]]]

# A cheap authenticated GET that never spends TTS credits.
_ELEVENLABS_USER_ENDPOINT = "https://api.elevenlabs.io/v1/user"
_ELEVENLABS_PROBE_TIMEOUT_S = 10.0
# The 401 `detail.status` values that mean the KEY ITSELF is bad. A scoped-but-valid key (one that
# can synthesise speech but lacks the `/v1/user` permission) authenticates fine and reports
# `missing_permissions` instead — still usable for narration, so it must NOT be rejected.
_ELEVENLABS_BAD_KEY_STATUSES = frozenset({"invalid_api_key", "needs_authorization"})


def _is_authenticated_status(status_code: int) -> bool:
    # A 2xx proves the key works; a 429 (rate-limited) still proves it authenticated.
    return 200 <= status_code < 300 or status_code == 429


async def _elevenlabs_http_probe(value: str) -> tuple[int, str]:
    import httpx

    async with httpx.AsyncClient(timeout=_ELEVENLABS_PROBE_TIMEOUT_S) as client:
        response = await client.get(_ELEVENLABS_USER_ENDPOINT, headers={"xi-api-key": value})
    # ElevenLabs errors carry {"detail": {"status": "..."}}; pull it out best-effort to tell a bad
    # key from a valid-but-scoped one (both return 401).
    detail_status = ""
    try:
        detail = response.json().get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("status"), str):
            detail_status = detail["status"]
    except Exception:
        detail_status = ""
    return response.status_code, detail_status


class ElevenLabsProbeValidator:
    """Validates the ElevenLabs key with a tiny authenticated call; passes other secrets through.

    A 2xx (or a 429 — rate-limited but authenticated) proves the key is valid. A 401 needs care:
    ElevenLabs returns 401 both for a genuinely bad key (``detail.status == "invalid_api_key"``) AND
    for a VALID key that merely lacks the ``/v1/user`` permission (``"missing_permissions"``) — a
    permission-scoped key can still narrate, so only the bad-key statuses reject; an authenticated
    401 passes (a key that truly can't synthesise just degrades the render to silent). Any other
    outcome is surfaced as un-verifiable. The probe is injectable; the value is never logged.
    """

    def __init__(self, *, probe: ElevenLabsProbe | None = None) -> None:
        self._probe = probe or _elevenlabs_http_probe

    async def validate(self, name: str, value: str) -> None:
        if name != "elevenlabs":
            return
        try:
            status_code, detail_status = await self._probe(value)
        except Exception as exc:  # network, etc. — couldn't verify
            raise SecretValidationError(
                f"Could not reach ElevenLabs to verify the key ({type(exc).__name__})."
            ) from exc
        if _is_authenticated_status(status_code):
            return
        if status_code == 401:
            if detail_status in _ELEVENLABS_BAD_KEY_STATUSES:
                raise SecretValidationError("ElevenLabs rejected this API key.")
            # Any other 401 — a known permission error (missing_permissions) or an unparseable body
            # — means the key authenticated; accept it (a key that truly can't TTS degrades the
            # render to silent rather than blocking the user from saving a real key).
            return
        raise SecretValidationError(f"Could not verify the ElevenLabs key (HTTP {status_code}).")


class CompositeSecretValidator:
    """Runs each member validator in turn.

    Every validator no-ops for a name that is not its own, so composing them covers all the keyed
    providers with one ``validate`` call.
    """

    def __init__(self, validators: Sequence[ISecretValidator]) -> None:
        self._validators = tuple(validators)

    async def validate(self, name: str, value: str) -> None:
        for validator in self._validators:
            await validator.validate(name, value)


class AcceptingValidator:
    """A validator that accepts everything — the deterministic no-network default for tests."""

    async def validate(self, name: str, value: str) -> None:
        return None
