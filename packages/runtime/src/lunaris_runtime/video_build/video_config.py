from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..run_config import resolve_config
from ..schema import VideoKind
from .video_lengths import target_seconds_for

# The per-user video config (explainer-video V6), keyed by the env var the run-config scope reads —
# the same mechanism that carries model selection (``LUNARIS_MODEL_*``). The API's config_store maps
# its logical ids (``videoEnabled`` …) to THESE names; a new key is a change in both places.
VIDEO_ENABLED_ENV = "LUNARIS_VIDEO_ENABLED"
VIDEO_VOICE_ENV = "LUNARIS_VIDEO_VOICE"
# A sub-toggle under the master: when off, the build skips the per-lesson videos but still makes the
# two course-level videos (summary trailer + topic overview). Defaults ON, so an unset value keeps
# the historical behaviour (every lesson gets a video).
VIDEO_LESSONS_ENABLED_ENV = "LUNARIS_VIDEO_LESSONS_ENABLED"
VIDEO_SUMMARY_SECONDS_ENV = "LUNARIS_VIDEO_SUMMARY_SECONDS"
VIDEO_OVERVIEW_SECONDS_ENV = "LUNARIS_VIDEO_OVERVIEW_SECONDS"
VIDEO_LESSON_SECONDS_ENV = "LUNARIS_VIDEO_LESSON_SECONDS"

# The bounds the length values are clamped to — defence in depth around whatever the UI offers (the
# API re-validates the same range at the write boundary). 15s is below the shortest sensible clip,
# 600s above the longest (the chaptered overview tops out ~5 min).
MIN_VIDEO_SECONDS = 15
MAX_VIDEO_SECONDS = 600

_SECONDS_ENV: dict[VideoKind, str] = {
    VideoKind.SUMMARY: VIDEO_SUMMARY_SECONDS_ENV,
    VideoKind.OVERVIEW: VIDEO_OVERVIEW_SECONDS_ENV,
    VideoKind.LESSON: VIDEO_LESSON_SECONDS_ENV,
}


@dataclass(frozen=True)
class VideoConfig:
    """One build's resolved video settings: whether video is on at all, whether to make the
    per-lesson videos, whether to narrate, and the target length per kind. Read from the run-config
    scope (the build path) or a resolved env-var map (the on-demand path); every field has a
    default, so an unset value never refuses — it falls back to the product default (master ON,
    lesson videos ON, voice ON, the per-kind ``target_seconds_for``).

    ``lessons_enabled`` is a sub-toggle of ``enabled``: with the master on but this off, the build
    still makes the two course-level videos (summary + overview) and only skips the per-lesson
    ones. The on-demand reader path is unaffected — it gates on ``enabled`` alone, so a user can
    still make a single lesson video by hand."""

    enabled: bool
    voice: bool
    lessons_enabled: bool
    summary_seconds: int
    overview_seconds: int
    lesson_seconds: int

    def target_seconds(self, kind: VideoKind) -> int:
        """The configured length for ``kind`` — what PLAN designs the contract to."""
        return {
            VideoKind.SUMMARY: self.summary_seconds,
            VideoKind.OVERVIEW: self.overview_seconds,
            VideoKind.LESSON: self.lesson_seconds,
        }[kind]


def resolve_video_config() -> VideoConfig:
    """The video config bound into the current run-config scope (the build path), falling back to
    the process env / product defaults. Read at enqueue time, inside the build task's config
    scope."""
    return _parse(resolve_config)


def video_config_from_map(config: Mapping[str, str] | None) -> VideoConfig:
    """The video config carried by a resolved env-var map (the gate + on-demand path), or all
    defaults when ``None``. Keyed by env-var name (e.g. ``LUNARIS_VIDEO_ENABLED``), like the
    run-config resolver returns."""
    get: Callable[[str], str | None] = (lambda _key: None) if config is None else config.get
    return _parse(get)


def _parse(get: Callable[[str], str | None]) -> VideoConfig:
    seconds = {kind: _as_seconds(get(env), kind) for kind, env in _SECONDS_ENV.items()}
    return VideoConfig(
        enabled=_as_bool(get(VIDEO_ENABLED_ENV), default=True),
        voice=_as_bool(get(VIDEO_VOICE_ENV), default=True),
        lessons_enabled=_as_bool(get(VIDEO_LESSONS_ENABLED_ENV), default=True),
        summary_seconds=seconds[VideoKind.SUMMARY],
        overview_seconds=seconds[VideoKind.OVERVIEW],
        lesson_seconds=seconds[VideoKind.LESSON],
    )


def _as_bool(value: str | None, *, default: bool) -> bool:
    # Unset OR malformed → the default (mirrors _as_seconds): the write boundary only stores
    # 'true'/'false', so a stray value here means a corrupted store, not an intent to disable.
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in ("true", "false"):
        return normalized == "true"
    return default


def _as_seconds(value: str | None, kind: VideoKind) -> int:
    """An in-bounds length, or the kind's product default when unset/unparseable — a malformed
    stored value must never abort a build, only fall back."""
    if value is None:
        return target_seconds_for(kind)
    try:
        seconds = int(value)
    except ValueError:
        return target_seconds_for(kind)
    return max(MIN_VIDEO_SECONDS, min(seconds, MAX_VIDEO_SECONDS))


# The product default when nothing is configured (master ON, voice ON, per-kind default lengths) —
# the coordinator's fallback when no per-user config was threaded in. Defined after ``_parse`` so
# the module-load call resolves.
DEFAULT_VIDEO_CONFIG = video_config_from_map(None)
