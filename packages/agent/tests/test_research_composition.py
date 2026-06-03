"""P7.2-T3 — the composition root key-gates the live researcher on ``SEARCH_API_KEY``.

With a search key the agent pipeline wires the real Tavily+Trafilatura researcher; without one it
falls back to the stub (research degrades to UNAVAILABLE), so the no-key CI path is deterministic.
"""

import pytest
from lunaris_agent.composition import _researcher_from_env
from lunaris_agent.subagents.standard_researcher import (
    ClaudeStandardResearcher,
    StubStandardResearcher,
)
from lunaris_grounding import TavilySearchProvider, TrafilaturaContentExtractor

_WORKER = "claude-haiku-4-5-20251001"


def test_researcher_is_stubbed_without_a_search_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — no search key configured.
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)

    # Act / Assert — the stub (UNAVAILABLE research) keeps the no-key path deterministic.
    assert isinstance(_researcher_from_env(_WORKER), StubStandardResearcher)


def test_researcher_is_live_when_the_search_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — a search key is present (constructing the provider touches no network).
    monkeypatch.setenv("SEARCH_API_KEY", "tvly-test-key")

    # Act
    researcher = _researcher_from_env(_WORKER)

    # Assert — the live researcher wired over the real Tavily search + Trafilatura extraction
    # adapters (not the stub), so a regression substituting a stub here would be caught.
    assert isinstance(researcher, ClaudeStandardResearcher)
    assert isinstance(researcher._search, TavilySearchProvider)
    assert isinstance(researcher._extractor, TrafilaturaContentExtractor)
