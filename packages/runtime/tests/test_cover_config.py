"""CoverConfig resolution (course-cover-images T10): the per-user cover settings map → CoverConfig.

Mirrors the video_config parser: every field defaults (an unset value never refuses), and a
malformed stored value falls back rather than aborting the enqueue.
"""

from lunaris_runtime.cover_build import (
    COVER_ENABLED_ENV,
    COVER_STYLE_PRESET_ENV,
    DEFAULT_COVER_CONFIG,
    cover_config_from_map,
)
from lunaris_runtime.schema import CoverStylePreset


def test_none_map_is_all_defaults() -> None:
    config = cover_config_from_map(None)
    assert config.enabled is True
    assert config.style_preset is CoverStylePreset.GENERAL
    assert config == DEFAULT_COVER_CONFIG


def test_reads_the_toggle_and_preset() -> None:
    config = cover_config_from_map({COVER_ENABLED_ENV: "false", COVER_STYLE_PRESET_ENV: "aurora"})
    assert config.enabled is False
    assert config.style_preset is CoverStylePreset.AURORA


def test_unknown_preset_falls_back_to_the_house_default() -> None:
    config = cover_config_from_map({COVER_STYLE_PRESET_ENV: "chartreuse"})
    assert config.style_preset is CoverStylePreset.GENERAL


def test_malformed_toggle_falls_back_to_enabled() -> None:
    config = cover_config_from_map({COVER_ENABLED_ENV: "yes-please"})
    # The write boundary only stores true/false, so a stray value defaults to on.
    assert config.enabled is True


def test_preset_is_case_insensitive() -> None:
    config = cover_config_from_map({COVER_STYLE_PRESET_ENV: "BluePrint"})
    assert config.style_preset is CoverStylePreset.BLUEPRINT
