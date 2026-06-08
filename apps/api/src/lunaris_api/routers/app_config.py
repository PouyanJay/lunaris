from fastapi import APIRouter, HTTPException, status

from ..config_store import ConfigError, ConfigKeyError, ConfigSetting
from ..dependencies import ConfigStoreDep, OptionalUserIdDep, UserConfigServiceDep
from ..schemas import ConfigSettingView, ConfigValue, ConfigView

router = APIRouter(prefix="/api/config", tags=["config"])


def _to_view(setting: ConfigSetting) -> ConfigSettingView:
    return ConfigSettingView(
        name=setting.name,
        value=setting.value,
        default=setting.default,
        kind=setting.kind,
        restart_required=setting.restart_required,
    )


@router.get("", response_model=ConfigView)
async def get_config(
    file_store: ConfigStoreDep,
    user_config: UserConfigServiceDep,
    owner_id: OptionalUserIdDep,
) -> ConfigView:
    """The non-secret configuration surface: each setting's value, default, kind, and restart flag.

    With auth on, this is the caller's OWN per-user config (model selection, from the DB); with auth
    off it's the process-wide file store (single-user dev, incl. operator LangSmith config). Values
    are shown (these are not secrets), unlike the write-only secret store.
    """
    settings = (
        await user_config.settings(user_id=owner_id)
        if owner_id is not None
        else file_store.settings()
    )
    return ConfigView(settings=[_to_view(s) for s in settings])


@router.put("/{name}", response_model=ConfigSettingView)
async def set_config(
    name: str,
    payload: ConfigValue,
    file_store: ConfigStoreDep,
    user_config: UserConfigServiceDep,
    owner_id: OptionalUserIdDep,
) -> ConfigSettingView:
    """Persist a config value, returning the updated setting.

    With auth on, it writes the caller's per-user config (model selection) to the DB — used by the
    next build via the run-config scope. With auth off, it persists to the file store + applies to
    the process env (a restart-required langsmith var takes effect on the next restart; model vars
    apply to the next build).
    """
    try:
        setting = (
            await user_config.set(user_id=owner_id, name=name, value=payload.value)
            if owner_id is not None
            else file_store.set(name, payload.value)
        )
    except ConfigKeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return _to_view(setting)
