"""The cover-pipeline composition root (general-template-fidelity review): the light-variant env
knob. ``LUNARIS_COVER_LIGHT_VARIANT`` parses strictly — only the string ``true`` (any case,
padded) turns the light twin on; unset, empty, ``false`` and malformed values all stay OFF, the
cost-saving default. Pinned here because this string comparison is the ONLY place the knob exists —
a refactor to truthiness (where ``"false"`` is truthy) would silently break the default."""

from pathlib import Path

import pytest
from lunaris_api.config import Settings
from lunaris_api.dependencies import get_cover_pipeline


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        config_path=tmp_path / "config.json",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),  # unset — the default
        ("", False),
        ("false", False),
        ("yes", False),  # malformed → OFF, never accidentally on
        ("true", True),
        (" TRUE ", True),  # padded/any-case still opts in
    ],
)
def test_light_variant_env_knob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None, expected: bool
) -> None:
    if value is None:
        monkeypatch.delenv("LUNARIS_COVER_LIGHT_VARIANT", raising=False)
    else:
        monkeypatch.setenv("LUNARIS_COVER_LIGHT_VARIANT", value)

    pipeline = get_cover_pipeline(_settings(tmp_path))

    assert pipeline._light_variant is expected
