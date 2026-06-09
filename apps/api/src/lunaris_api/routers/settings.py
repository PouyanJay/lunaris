from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..capabilities import CapabilityStatus, resolve_capabilities
from ..config import Settings, get_settings
from ..dependencies import (
    SecretStoreDep,
    SecretValidatorDep,
    explain_is_available,
    pipeline_supports_lesson_regeneration,
)
from ..schemas import CapabilityStatusView, SecretStatusView, SecretValue, SettingsView
from ..secrets import (
    KNOWN_SECRETS,
    SecretStatus,
    SecretValidationError,
    contains_control_characters,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_view(status_: SecretStatus) -> SecretStatusView:
    return SecretStatusView(name=status_.name, is_set=status_.is_set, last4=status_.last4)


def _to_capability_view(status_: CapabilityStatus) -> CapabilityStatusView:
    return CapabilityStatusView(
        capability=status_.capability, mode=status_.mode, provider=status_.provider
    )


@router.get("", response_model=SettingsView)
def get_settings_view(
    store: SecretStoreDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SettingsView:
    """The settings surface: each secret's status (set/unset + last4) and the pipeline mode.

    Never returns a secret value — only whether it is set and its last four characters.
    """
    statuses = store.statuses()
    set_names = {s.name for s in statuses if s.is_set}
    return SettingsView(
        secrets=[_to_view(s) for s in statuses],
        pipeline=settings.pipeline,
        supports_lesson_regeneration=pipeline_supports_lesson_regeneration(settings.pipeline),
        supports_explain=explain_is_available(),
        byok_enabled=settings.has_byok,
        per_user_config_enabled=settings.has_auth,
        capabilities=[
            _to_capability_view(c) for c in resolve_capabilities(lambda name: name in set_names)
        ],
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
    # Guard before the probe. .env line-injection: a newline could split the value into a second
    # KEY=value entry. The 400 detail is value-free (a Pydantic 422 would echo the value back).
    if not value or contains_control_characters(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Secret value must be non-empty and free of control characters.",
        )
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
