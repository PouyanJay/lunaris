"""P7.1 — gap-scoped, level-aware extraction (offline, deterministic).

The actual KC-level scoping is the model's job (prompt-driven), so it's proven end-to-end by the
key-gated live eval in ``test_gap_extraction_eval``. Here we prove deterministically the two things
that DON'T need a model: ``build_extraction_prompt`` instructs the model to scope to the gap for a
non-novice brief (and to teach foundations for a novice / no brief), and the extract_concepts tool
actually passes the draft's brief + frontier into the extractor.
"""

import pytest
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_extract_concepts_tool
from lunaris_agent.subagents.concept_extractor import Extraction, build_extraction_prompt
from lunaris_runtime.schema import (
    BloomLevel,
    CourseBrief,
    KnowledgeComponent,
    Level,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
)

_FULL_LADDER = "INCLUDING the foundational prerequisites"
_GAP_INSTRUCTION = "Do NOT include foundational"


def test_build_extraction_prompt_scopes_to_the_gap_for_an_advanced_brief() -> None:
    # Arrange — an advanced goal with a stated prior + a known frontier.
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        target_level=Level.ADVANCED,
        assumed_prior="strong everyday English (CLB 8-9)",
    )

    # Act
    prompt = build_extraction_prompt("English", brief, ["the English alphabet", "basic grammar"])

    # Assert — the prompt carries the gap framing (goal, level, prior, the frontier to skip) and
    # drops the novice "teach the whole ladder" instruction.
    assert "reach CLB 10" in prompt
    assert "advanced" in prompt
    assert "strong everyday English (CLB 8-9)" in prompt
    assert "the English alphabet" in prompt
    assert "basic grammar" in prompt
    assert _GAP_INSTRUCTION in prompt
    assert _FULL_LADDER not in prompt


def test_build_extraction_prompt_teaches_foundations_for_a_novice_brief() -> None:
    brief = CourseBrief(subject="Knitting", goal="knit a scarf", target_level=Level.NOVICE)

    prompt = build_extraction_prompt("Knitting", brief, [])

    assert _FULL_LADDER in prompt
    assert "Knitting" in prompt
    assert _GAP_INSTRUCTION not in prompt


def test_build_extraction_prompt_defaults_to_the_full_ladder_without_a_brief() -> None:
    # The legacy / orchestrator path passes no brief — behavior is unchanged (novice full ladder).
    prompt = build_extraction_prompt("Binary search", None, [])

    assert _FULL_LADDER in prompt
    assert "Binary search" in prompt


@pytest.mark.parametrize("level", [Level.INTERMEDIATE, Level.ADVANCED, Level.EXPERT])
def test_build_extraction_prompt_scopes_for_every_non_novice_level(level: Level) -> None:
    brief = CourseBrief(subject="s", goal="g", target_level=level)

    prompt = build_extraction_prompt("s", brief, ["known thing"])

    assert _GAP_INSTRUCTION in prompt
    assert _FULL_LADDER not in prompt


@pytest.mark.parametrize("level", [Level.NOVICE, Level.NOT_APPLICABLE])
def test_build_extraction_prompt_uses_the_full_ladder_for_novice_and_na(level: Level) -> None:
    brief = CourseBrief(subject="s", goal="g", target_level=level)

    prompt = build_extraction_prompt("s", brief, [])

    assert _FULL_LADDER in prompt
    assert _GAP_INSTRUCTION not in prompt


def test_build_extraction_prompt_grounds_in_researched_competencies() -> None:
    # Arrange — a non-novice brief whose research grounded the standard's real competencies.
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        target_level=Level.ADVANCED,
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=["hear implied intent in speech", "read authorial stance"],
            sources=[ResearchSource(url="https://www.canada.ca/clb-10")],
        ),
    )

    # Act
    prompt = build_extraction_prompt("English", brief, ["the alphabet"])

    # Assert — the extractor is told to derive the KCs from the researched competencies, so the gap
    # is the standard's actual competencies rather than the model's memory of them.
    assert "hear implied intent in speech" in prompt
    assert "read authorial stance" in prompt


def test_build_extraction_prompt_omits_competency_grounding_without_research() -> None:
    # A gap brief with no research grounds on the level alone — no fabricated competency block.
    brief = CourseBrief(subject="s", goal="g", target_level=Level.ADVANCED)

    prompt = build_extraction_prompt("s", brief, ["known thing"])

    assert "researched competencies" not in prompt.lower()


def test_build_extraction_prompt_does_not_ground_the_novice_path_even_with_research() -> None:
    # Competency grounding is gap-scoped only: a NOVICE brief carrying research must still teach the
    # full ladder with no competency block (grounding lives inside the non-novice branch).
    brief = CourseBrief(
        subject="English",
        goal="speak basic phrases",
        target_level=Level.NOVICE,
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=["greet politely"],
            sources=[ResearchSource(url="https://example.com")],
        ),
    )

    prompt = build_extraction_prompt("English", brief, [])

    assert _FULL_LADDER in prompt
    assert "greet politely" not in prompt


def test_build_extraction_prompt_handles_an_empty_frontier_for_an_advanced_brief() -> None:
    # An advanced level with no enumerated frontier still scopes — it falls back to a generic floor.
    brief = CourseBrief(subject="s", goal="g", target_level=Level.ADVANCED)

    prompt = build_extraction_prompt("s", brief, [])

    assert _GAP_INSTRUCTION in prompt
    assert "the general foundations for this level" in prompt


class _RecordingExtractor:
    """Captures the kwargs the extract_concepts tool passes, to prove the wiring."""

    def __init__(self, extraction: Extraction) -> None:
        self._extraction = extraction
        self.calls: list[dict[str, object]] = []

    async def extract(
        self,
        topic: str,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> Extraction:
        self.calls.append({"topic": topic, "brief": brief, "frontier": frontier})
        return self._extraction


async def test_extract_concepts_tool_passes_the_brief_and_frontier_from_the_draft() -> None:
    # Arrange — a draft carrying an interpreted brief + a modeled frontier (P7.0/P7.1 upstream).
    draft = CourseDraft(topic="English", course_id="c", run_id="r")
    draft.brief = CourseBrief(subject="English", goal="reach CLB 10", target_level=Level.ADVANCED)
    draft.frontier = ["the alphabet", "basic vocabulary"]
    kc = KnowledgeComponent(
        id="x", label="X", definition="d", difficulty=0.5, bloom_ceiling=BloomLevel.APPLY
    )
    extractor = _RecordingExtractor(Extraction(kcs=[kc], goal_id="x"))
    tool = make_extract_concepts_tool(extractor, draft)

    # Act
    await tool.ainvoke({"topic": "English"})

    # Assert — the tool threaded the draft's brief + frontier into the extractor (the gap inputs).
    assert extractor.calls[0]["brief"] is draft.brief
    assert extractor.calls[0]["frontier"] == ["the alphabet", "basic vocabulary"]
