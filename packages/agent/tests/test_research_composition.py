"""T3 — search is no longer key-gated: the composition root wires Tavily when ``SEARCH_API_KEY`` is
set, else keyless DuckDuckGo, so research (and discovery / curation) run keyless, not stubbed.
"""

import pytest
from lunaris_agent.composition._grounding import _search_provider_from_env
from lunaris_agent.composition._subagents import _researcher_from_env
from lunaris_agent.subagents.standard_researcher import ClaudeStandardResearcher
from lunaris_grounding import (
    DuckDuckGoSearchProvider,
    TavilySearchProvider,
    TrafilaturaContentExtractor,
)

_WORKER = "claude-haiku-4-5-20251001"


def test_search_provider_is_duckduckgo_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)

    assert isinstance(_search_provider_from_env(), DuckDuckGoSearchProvider)


def test_search_provider_is_tavily_when_the_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEARCH_API_KEY", "tvly-test-key")

    assert isinstance(_search_provider_from_env(), TavilySearchProvider)


def test_researcher_is_keyless_via_duckduckgo_without_a_search_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No search key — research runs on DuckDuckGo rather than degrading to the UNAVAILABLE stub.
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)

    researcher = _researcher_from_env(_WORKER)

    assert isinstance(researcher, ClaudeStandardResearcher)
    assert isinstance(researcher._search, DuckDuckGoSearchProvider)


def test_researcher_uses_tavily_when_the_search_key_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # A search key is present (constructing the provider touches no network).
    monkeypatch.setenv("SEARCH_API_KEY", "tvly-test-key")

    researcher = _researcher_from_env(_WORKER)

    assert isinstance(researcher._search, TavilySearchProvider)
    assert isinstance(researcher._extractor, TrafilaturaContentExtractor)
