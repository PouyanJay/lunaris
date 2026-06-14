"""Per-user video config (explainer-video V6-T0): the build's video settings, resolved from the
run-config scope (the build path) or a resolved env-var map (the gate + on-demand path).

Every field has a product default, so an unset value never refuses — master ON, voice ON, the
per-kind ``target_seconds_for`` lengths. Out-of-bounds / malformed lengths fall back to the default
rather than abort a build (defence in depth around whatever the UI offers)."""

import pytest
from lunaris_runtime.run_config import run_config
from lunaris_runtime.schema import VideoKind
from lunaris_runtime.video_build import (
    DEFAULT_VIDEO_CONFIG,
    MAX_VIDEO_SECONDS,
    MIN_VIDEO_SECONDS,
    resolve_video_config,
    target_seconds_for,
    video_config_from_map,
)
from lunaris_runtime.video_build.video_config import (
    VIDEO_ENABLED_ENV,
    VIDEO_LESSON_SECONDS_ENV,
    VIDEO_OVERVIEW_SECONDS_ENV,
    VIDEO_SUMMARY_SECONDS_ENV,
    VIDEO_VOICE_ENV,
)


def test_an_empty_map_is_all_product_defaults() -> None:
    # Unset everywhere → the product defaults: master ON, voice ON, per-kind default lengths.
    config = video_config_from_map(None)
    assert config.enabled is True
    assert config.voice is True
    for kind in VideoKind:
        assert config.target_seconds(kind) == target_seconds_for(kind)


def test_default_video_config_matches_an_empty_map() -> None:
    assert video_config_from_map({}) == DEFAULT_VIDEO_CONFIG


def test_master_toggle_off_is_read_from_the_map() -> None:
    config = video_config_from_map({VIDEO_ENABLED_ENV: "false"})
    assert config.enabled is False


def test_voice_toggle_off_is_read_from_the_map() -> None:
    config = video_config_from_map({VIDEO_VOICE_ENV: "false"})
    assert config.voice is False
    assert config.enabled is True  # master untouched


def test_per_kind_lengths_are_read_from_the_map() -> None:
    # Each kind's env var maps to its OWN length — a swapped mapping would surface here.
    config = video_config_from_map(
        {
            VIDEO_SUMMARY_SECONDS_ENV: "45",
            VIDEO_OVERVIEW_SECONDS_ENV: "240",
            VIDEO_LESSON_SECONDS_ENV: "90",
        }
    )
    assert config.target_seconds(VideoKind.SUMMARY) == 45
    assert config.target_seconds(VideoKind.OVERVIEW) == 240
    assert config.target_seconds(VideoKind.LESSON) == 90


def test_an_unset_kind_keeps_its_default_length() -> None:
    config = video_config_from_map({VIDEO_LESSON_SECONDS_ENV: "90"})
    assert config.target_seconds(VideoKind.LESSON) == 90
    assert config.target_seconds(VideoKind.SUMMARY) == target_seconds_for(VideoKind.SUMMARY)
    assert config.target_seconds(VideoKind.OVERVIEW) == target_seconds_for(VideoKind.OVERVIEW)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (str(MAX_VIDEO_SECONDS + 1000), MAX_VIDEO_SECONDS),  # over the ceiling → clamped
        (str(MIN_VIDEO_SECONDS - 5), MIN_VIDEO_SECONDS),  # under the floor → clamped
        ("not-a-number", target_seconds_for(VideoKind.LESSON)),  # malformed → default
    ],
)
def test_out_of_bounds_or_malformed_lengths_fall_back_safely(raw: str, expected: int) -> None:
    # A bad stored value must never abort a build — it falls back to an in-bounds value.
    config = video_config_from_map({VIDEO_LESSON_SECONDS_ENV: raw})
    assert config.target_seconds(VideoKind.LESSON) == expected


def test_resolve_reads_the_run_config_scope() -> None:
    # The build path: resolve_video_config reads whatever the run-config scope carries (env-var
    # keyed, the same scope the tenant's model selection rides in).
    with run_config({VIDEO_ENABLED_ENV: "false", VIDEO_LESSON_SECONDS_ENV: "60"}):
        config = resolve_video_config()
    assert config.enabled is False
    assert config.target_seconds(VideoKind.LESSON) == 60


def test_resolve_outside_a_scope_is_defaults() -> None:
    # No scope (and no env) → product defaults, never a refusal.
    config = resolve_video_config()
    assert config.enabled is True
    assert config.voice is True
