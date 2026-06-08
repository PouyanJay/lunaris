"""Shared test doubles for the API suite (not collected as tests — the leading underscore)."""

from lunaris_api.secrets import SecretValidationError


class RejectingValidator:
    """An ``ISecretValidator`` that rejects every key — models a provider refusing a bad key."""

    async def validate(self, name: str, value: str) -> None:
        raise SecretValidationError("provider rejected the key")
