"""P5: the API's default course pipeline is the real deep-agent harness.

The product default is the agent harness (``LUNARIS_PIPELINE=agent``), not the legacy single-shot
orchestrator. ``make run`` still guards on a reachable key and falls back to the stub; this pins the
in-process default the API resolves when nothing is set."""

from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path

import pytest
from lunaris_api.config import Settings, get_settings


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


def test_env_file_defaults_to_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — the secret store's single source of truth is .env, loaded at startup via --env-file.
    monkeypatch.delenv("LUNARIS_ENV_FILE", raising=False)

    # Act
    settings = get_settings()

    # Assert
    assert settings.env_file == Path(".env")


def test_env_file_override_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — tests point the store at a throwaway file so they never touch the real .env.
    monkeypatch.setenv("LUNARIS_ENV_FILE", "/tmp/throwaway.env")

    # Act
    settings = get_settings()

    # Assert
    assert settings.env_file == Path("/tmp/throwaway.env")


def test_a_live_sessions_ceiling_leaves_room_for_two_calls_a_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lunaris Live, Phase 2b T9. The per-session USD ceiling is a runaway guard, not a ration
    (P2a): the clock bounds an ordinary sitting, and the ceiling only binds when something is
    wrong. P2b T5 made every keyed turn two model calls (the lesson and its material) instead of
    one, and at the P2a eval's ≈$0.10 a turn for a lesson plus a grade an ordinary 15-20 turn
    sitting now lands between $2.25 and $4, so the old $2 default would end sittings that were
    going well. Doubled with the calls, and pinned so the next tier that adds a call has to look
    here."""
    monkeypatch.delenv("LUNARIS_LIVE_SESSION_BUDGET_USD", raising=False)

    settings = get_settings()

    assert settings.live_session_budget_usd == 4.0
    # The env reader and the model carry the number separately (as every field here does), and a
    # ``Settings(...)`` built directly, the whole test suite's ``_settings`` helpers, reads the
    # model's. Both are pinned so the two cannot drift.
    declared = {field.name: field.default for field in fields(Settings)}
    assert declared["live_session_budget_usd"] == 4.0
