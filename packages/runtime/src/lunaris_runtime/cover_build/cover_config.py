from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..run_config import resolve_config
from ..schema import CoverStylePreset

# The per-user cover config (course-cover-images tunability), keyed by the env var the run-config
# scope reads — the same mechanism that carries model selection + the video toggles. The API's
# config_store maps its logical ids (``coverGenerationEnabled`` / ``coverStylePreset``) to THESE
# names; a new key is a change in both places (and the user_runtime_config CHECK).
COVER_ENABLED_ENV = "LUNARIS_COVER_ENABLED"
COVER_STYLE_PRESET_ENV = "LUNARIS_COVER_STYLE_PRESET"

# The house default when nothing is configured — the night-sky editorial look.
_DEFAULT_PRESET = CoverStylePreset.NOCTURNE


@dataclass(frozen=True)
class CoverConfig:
    """One build's resolved cover settings: whether to auto-generate a cover at all, and which
    art-direction preset to use. Read from the run-config scope (the build path) or a resolved
    env-var map (the enqueue gate). Every field has a default, so an unset value never refuses — it
    falls back to the product default (generation ON, the ``nocturne`` preset)."""

    enabled: bool
    style_preset: CoverStylePreset


def resolve_cover_config() -> CoverConfig:
    """The cover config bound into the current run-config scope, falling back to the process env /
    product defaults."""
    return _parse(resolve_config)


def cover_config_from_map(config: Mapping[str, str] | None) -> CoverConfig:
    """The cover config carried by a resolved env-var map (the build-completion enqueue gate), or
    all defaults when ``None``. Keyed by env-var name, like the run-config resolver returns."""
    get: Callable[[str], str | None] = (lambda _key: None) if config is None else config.get
    return _parse(get)


def _parse(get: Callable[[str], str | None]) -> CoverConfig:
    return CoverConfig(
        enabled=_as_bool(get(COVER_ENABLED_ENV), default=True),
        style_preset=_as_preset(get(COVER_STYLE_PRESET_ENV)),
    )


def _as_bool(value: str | None, *, default: bool) -> bool:
    # Unset OR malformed → the default: the write boundary only stores 'true'/'false', so a stray
    # value here means a corrupted store, not an intent to disable.
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in ("true", "false"):
        return normalized == "true"
    return default


def _as_preset(value: str | None) -> CoverStylePreset:
    """A known preset, or the house default when unset/unknown — a malformed stored value must never
    abort the enqueue, only fall back to ``nocturne``."""
    if value is None:
        return _DEFAULT_PRESET
    try:
        return CoverStylePreset(value.strip().lower())
    except ValueError:
        return _DEFAULT_PRESET


# The product default when nothing is configured (generation ON, nocturne). Defined after ``_parse``
# so the module-load call resolves.
DEFAULT_COVER_CONFIG = cover_config_from_map(None)
