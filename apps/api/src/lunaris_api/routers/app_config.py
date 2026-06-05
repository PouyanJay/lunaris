from fastapi import APIRouter, HTTPException, status

from ..config_store import ConfigError, ConfigKeyError, ConfigSetting
from ..dependencies import ConfigStoreDep
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
def get_config(store: ConfigStoreDep) -> ConfigView:
    """The non-secret configuration surface: each setting's value, default, kind, and restart flag.

    Values are shown (these are not secrets), unlike the write-only secret store.
    """
    return ConfigView(settings=[_to_view(s) for s in store.settings()])


@router.put("/{name}", response_model=ConfigSettingView)
def set_config(name: str, payload: ConfigValue, store: ConfigStoreDep) -> ConfigSettingView:
    """Persist a config value + apply it to the runtime environment, returning the updated setting.

    A change to a restart-required setting (the langsmith vars, read by the SDK at startup) takes
    effect on the next restart; model vars apply to the next build.
    """
    try:
        return _to_view(store.set(name, payload.value))
    except ConfigKeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
