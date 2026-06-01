from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..dependencies import (
    SecretStoreDep,
    SecretValidatorDep,
    pipeline_supports_lesson_regeneration,
)
from ..schemas import SecretStatusView, SecretValue, SettingsView
from ..secrets import KNOWN_SECRETS, SecretStatus, SecretValidationError

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_view(status_: SecretStatus) -> SecretStatusView:
    return SecretStatusView(name=status_.name, is_set=status_.is_set, last4=status_.last4)


@router.get("", response_model=SettingsView)
def get_settings_view(
    store: SecretStoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SettingsView:
    """The settings surface: each secret's status (set/unset + last4) and the pipeline mode.

    Never returns a secret value — only whether it is set and its last four characters.
    """
    return SettingsView(
        secrets=[_to_view(s) for s in store.statuses()],
        pipeline=settings.pipeline,
        supports_lesson_regeneration=pipeline_supports_lesson_regeneration(settings.pipeline),
    )


@router.put("/secrets/{name}", response_model=SecretStatusView)
async def set_secret(
    name: str,
    payload: SecretValue,
    store: SecretStoreDep,
    validator: SecretValidatorDep,
) -> SecretStatusView:
    """Validate and store a secret. The value is validated with a cheap probe before saving;
    on success it is persisted + applied to the runtime, and only its status is returned."""
    if name not in KNOWN_SECRETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown secret: {name}")
    value = payload.value.get_secret_value()
    try:
        await validator.validate(name, value)
    except SecretValidationError as exc:
        # The message is safe (no value); the value itself is never logged or echoed.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _to_view(store.set(name, value))


@router.delete("/secrets/{name}", response_model=SecretStatusView)
def clear_secret(name: str, store: SecretStoreDep) -> SecretStatusView:
    """Clear a stored secret (removes it from the store and the runtime environment)."""
    if name not in KNOWN_SECRETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown secret: {name}")
    return _to_view(store.clear(name))
