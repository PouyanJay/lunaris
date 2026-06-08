import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Logical config id (the web/API contract) → the environment variable the runtime reads. Unlike
# secrets these are NON-secret: their values are shown in the UI. Populating os.environ is how a
# UI-provided value reaches the runtime adapters (and, at startup, the langsmith SDK) without
# threading it through every call site.
KNOWN_CONFIG: dict[str, str] = {
    "langsmithTracing": "LANGSMITH_TRACING",
    "langsmithProject": "LANGSMITH_PROJECT",
    "modelStrong": "LUNARIS_MODEL_STRONG",
    "modelWorker": "LUNARIS_MODEL_WORKER",
}

# How the web renders each control: ``toggle`` = on/off; ``model`` = a known-model dropdown;
# ``text`` = a free-text field.
ConfigKind = Literal["toggle", "text", "model"]

# Defaults mirror the runtime's own fallbacks (composition.py `_DEFAULT_STRONG`/`_DEFAULT_WORKER`,
# the langsmith env conventions) so an unset value reads the same in the UI as the code would use.
_DEFAULTS: dict[str, str] = {
    "langsmithTracing": "false",
    "langsmithProject": "lunaris",
    "modelStrong": "claude-opus-4-8",
    "modelWorker": "claude-haiku-4-5-20251001",
}

_KINDS: dict[str, ConfigKind] = {
    "langsmithTracing": "toggle",
    "langsmithProject": "text",
    "modelStrong": "model",
    "modelWorker": "model",
}

# Values consumed at process start (the langsmith SDK) only take effect after a restart; the UI
# flags these. The model vars are read per build, so they apply to the next build with no restart.
_RESTART_REQUIRED: frozenset[str] = frozenset({"langsmithTracing", "langsmithProject"})

_MAX_VALUE_LEN = 200


class ConfigError(ValueError):
    """A rejected config write. Mapped to 4xx by the router."""


class ConfigKeyError(ConfigError):
    """An unknown config key — mapped to 404 (distinct from a 422 invalid value)."""


@dataclass(frozen=True)
class ConfigSetting:
    """One non-secret setting: its effective value, its default, how to render it, and whether a
    change needs a restart to take effect."""

    name: str
    value: str
    default: str
    kind: ConfigKind
    restart_required: bool


def validate_config_value(name: str, value: str) -> str:
    """Trim + validate one config value against its kind. Shared by the file store and the per-user
    service so both reject the same way; it also guards the key against ``KNOWN_CONFIG`` (the
    per-user service narrows to its own surface BEFORE calling this). Raises ``ConfigKeyError``
    (unknown key) / ``ConfigError`` (bad value)."""
    if name not in KNOWN_CONFIG:
        raise ConfigKeyError(f"Unknown config key: {name}")
    cleaned = value.strip()
    if _KINDS[name] == "toggle":
        if cleaned not in ("true", "false"):
            raise ConfigError(f"{name} must be 'true' or 'false'")
        return cleaned
    # Model ids are free-form — a new model needs no backend release; the UI offers a shortlist.
    if not cleaned:
        raise ConfigError(f"{name} must not be empty")
    if len(cleaned) > _MAX_VALUE_LEN:
        raise ConfigError(f"{name} is too long (max {_MAX_VALUE_LEN} chars)")
    return cleaned


def build_config_setting(name: str, value: str | None) -> ConfigSetting:
    """A ``ConfigSetting`` for ``name`` carrying ``value`` (or its default when ``None``) — the one
    place a stored value is paired with its default/kind/restart metadata."""
    return ConfigSetting(
        name=name,
        value=value if value is not None else _DEFAULTS[name],
        default=_DEFAULTS[name],
        kind=_KINDS[name],
        restart_required=name in _RESTART_REQUIRED,
    )


class ConfigStore:
    """A persisted store for non-secret runtime configuration (local-dev operator settings).

    Mirrors ``SecretStore`` — values are (a) persisted to a gitignored JSON file so they survive
    restarts and (b) applied to ``os.environ`` so the runtime adapters (and, at startup, the
    langsmith SDK) pick them up. UNLIKE secrets the values are shown: ``settings()`` returns each
    value, its default, kind, and restart flag. The file is plain (not 0600) — nothing secret here.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._values: dict[str, str] = self._load()
        self._apply_to_env()

    def settings(self) -> list[ConfigSetting]:
        return [self._setting(name) for name in KNOWN_CONFIG]

    def set(self, name: str, value: str) -> ConfigSetting:
        cleaned = validate_config_value(name, value)
        self._values[name] = cleaned
        self._persist()
        os.environ[KNOWN_CONFIG[name]] = cleaned
        return self._setting(name)

    # --- internals ----------------------------------------------------------

    def _setting(self, name: str) -> ConfigSetting:
        return build_config_setting(name, self._values.get(name))

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        data = json.loads(self._path.read_text())
        return {k: str(v) for k, v in data.items() if k in KNOWN_CONFIG}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._values, indent=2))

    def _apply_to_env(self) -> None:
        for name, value in self._values.items():
            os.environ[KNOWN_CONFIG[name]] = value
