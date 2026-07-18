"""Shared test doubles for the API suite (not collected as tests — the leading underscore)."""

from lunaris_api.secrets import SecretValidationError
from lunaris_runtime.persistence import (
    CoverImageTransform,
    InMemoryCoverStorage,
    PersistenceError,
)


class CannotResizeCoverStorage(InMemoryCoverStorage):
    """Cover storage that signs a master but not a resized derivative — image transformations
    disabled, or a transform-specific quota / hiccup. Exercises the thumb degrade-to-None path: the
    master + provenance still resolve; only the transformed (thumb) sign raises."""

    async def signed_url(
        self,
        *,
        path: str,
        expires_in_seconds: int = 3600,
        transform: CoverImageTransform | None = None,
    ) -> str:
        if transform is not None:
            raise PersistenceError("transformations unavailable")
        return await super().signed_url(path=path, expires_in_seconds=expires_in_seconds)


class RejectingValidator:
    """An ``ISecretValidator`` that rejects every key — models a provider refusing a bad key."""

    async def validate(self, name: str, value: str) -> None:
        raise SecretValidationError("provider rejected the key")


class AcceptingValidator:
    """An ``ISecretValidator`` that accepts every key — for tests not exercising the probe."""

    async def validate(self, name: str, value: str) -> None:
        return None
