from ..config_store import (
    ConfigKeyError,
    ConfigSetting,
    build_config_setting,
    validate_config_value,
)
from .store_protocol import PER_USER_CONFIG, IUserConfigStore


class UserConfigService:
    """The per-user config surface the API serves when auth is on — model selection, scoped to one
    tenant. Mirrors the file ``ConfigStore.settings()/set()`` shape (so the router is uniform) but
    reads/writes the per-user store instead of the process env, and exposes ONLY the per-user keys
    (LangSmith stays operator-only). Values + defaults are shown (config is non-secret)."""

    def __init__(self, store: IUserConfigStore) -> None:
        self._store = store

    async def settings(self, *, user_id: str) -> list[ConfigSetting]:
        """Every per-user setting with its effective value (the user's choice, or the default)."""
        stored = await self._store.get_all(user_id=user_id)
        return [build_config_setting(name, stored.get(name)) for name in PER_USER_CONFIG]

    async def set(self, *, user_id: str, name: str, value: str) -> ConfigSetting:
        """Validate + persist one per-user config value, returning the updated setting. Rejects any
        key outside the per-user surface (e.g. an operator-only LangSmith key) with a 404-mapped
        ``ConfigKeyError``, so a tenant can't write operator config through this door."""
        if name not in PER_USER_CONFIG:
            raise ConfigKeyError(f"Unknown config key: {name}")
        cleaned = validate_config_value(name, value)
        await self._store.set(user_id=user_id, key=name, value=cleaned)
        return build_config_setting(name, cleaned)
