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


class AcceptingValidator:
    """A validator that accepts everything — the deterministic no-network default for tests."""

    async def validate(self, name: str, value: str) -> None:
        return None
