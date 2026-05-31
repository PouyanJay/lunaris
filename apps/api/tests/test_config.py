"""P5: the API's default course pipeline is the real deep-agent harness.

The product default is the agent harness (``LUNARIS_PIPELINE=agent``), not the legacy single-shot
orchestrator. ``make run`` still guards on a reachable key and falls back to the stub; this pins the
in-process default the API resolves when nothing is set."""

from collections.abc import Iterator

import pytest
from lunaris_api.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    # get_settings is lru_cached; clear it around each test so env changes are read fresh.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_pipeline_is_the_agent_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — nothing set in the environment.
    monkeypatch.delenv("LUNARIS_PIPELINE", raising=False)

    # Act
    settings = get_settings()

    # Assert — the real deep-agent harness is the default backend.
    assert settings.pipeline == "agent"


def test_pipeline_env_override_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — an explicit override (and case-insensitive).
    monkeypatch.setenv("LUNARIS_PIPELINE", "STUB")

    # Act
    settings = get_settings()

    # Assert — the explicit toggle always wins, normalised to lower case.
    assert settings.pipeline == "stub"
