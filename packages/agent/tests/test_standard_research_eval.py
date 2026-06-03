"""P7.2 — the research-grounding eval (live, key-gated).

The headline guarantee of the research stage: a named standard is grounded in REAL competency
descriptors carried by REAL sources, not the model's memory. Deselected by default; run with a live
Anthropic key AND a SEARCH_API_KEY via ``-m eval``. The offline ``test_standard_researcher`` proves
the orchestration deterministically; this proves the end-to-end outcome against the live web.
"""

import os

import pytest
from lunaris_agent.subagents.standard_researcher import ClaudeStandardResearcher
from lunaris_grounding import TavilySearchProvider, TrafilaturaContentExtractor
from lunaris_runtime.schema import (
    CourseBrief,
    Level,
    ResearchStatus,
    StandardKind,
    TargetStandard,
)

pytestmark = pytest.mark.eval

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"


async def test_clb_10_is_grounded_in_real_competencies_with_provenance() -> None:
    # Arrange — the motivating case: an externally-defined standard with a known authority body.
    # The eval needs BOTH a live search backend and a live model; skip (not fail) if either is
    # absent, so `-m eval` with only one key skips cleanly rather than crashing mid-distillation.
    if not os.getenv("SEARCH_API_KEY"):
        pytest.skip("SEARCH_API_KEY unset; the research-grounding eval needs a live search backend")
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY unset; the research-grounding eval needs a live model")
    researcher = ClaudeStandardResearcher(
        os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER),
        TavilySearchProvider(),
        TrafilaturaContentExtractor(),
    )
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10 across listening, reading, writing, and speaking",
        target_standard=TargetStandard(
            name="CLB 10", kind=StandardKind.EXTERNAL_STANDARD, authority_hint="canada.ca"
        ),
        target_level=Level.ADVANCED,
        needs_research=True,
    )

    # Act
    research = await researcher.research(brief)

    # Assert — grounding actually happened (not the honest no-source degradation), real competencies
    # were distilled, and every cited source carries structural provenance (a real URL + a stamp).
    assert research.status is not ResearchStatus.UNAVAILABLE, (
        "the researcher degraded to UNAVAILABLE — no source was reachable for CLB 10 grounding"
    )
    assert research.competencies, "no competency descriptors were distilled"
    assert research.sources, "grounded research must cite at least one source"
    for source in research.sources:
        assert source.url.startswith("http"), f"source has no real provenance URL: {source.url}"
        assert source.fetched_at, "source is missing its fetched_at provenance stamp"
