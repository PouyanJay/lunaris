"""P7.2 — the research_standard tool's recording contract + honest degradation.

The integration test (test_agent_course_build) proves the stage flows through the real harness and
surfaces on the transcript; these unit tests pin the tool's two direct responsibilities the harness
relies on: it records the grounded findings on ``draft.brief.research`` (so extraction + the
curriculum architect design against the real standard, not the model's memory), and it degrades
honestly to ``UNAVAILABLE`` — without calling the researcher or crashing — when the brief is gone.
"""

import pytest
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_research_standard_tool
from lunaris_agent.subagents.standard_researcher import StubStandardResearcher
from lunaris_runtime.schema import (
    CourseBrief,
    Level,
    ProgressStage,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
    TrustTier,
)

_RESEARCH = StandardResearch(
    status=ResearchStatus.COMPLETE,
    competencies=["hear implied intent in speech"],
    sources=[
        ResearchSource(
            url="https://www.canada.ca/clb-10",
            title="CLB 10",
            trust_tier=TrustTier.OFFICIAL,
        )
    ],
)


class _RecordingProgress:
    """A progress reporter test double that records the stages it was asked to emit."""

    def __init__(self) -> None:
        self.stages: list[ProgressStage] = []

    async def emit(self, stage: ProgressStage, label: str, **counts: object) -> None:
        self.stages.append(stage)


async def test_research_standard_records_findings_on_the_brief() -> None:
    # Arrange — a draft whose brief was interpreted; the tool should ground it via the researcher.
    draft = CourseDraft(topic="Improve my English to CLB 10", course_id="c", run_id="r")
    draft.brief = CourseBrief(
        subject="English proficiency", goal="reach CLB 10", target_level=Level.ADVANCED
    )
    draft.progress = _RecordingProgress()  # type: ignore[assignment]
    tool = make_research_standard_tool(StubStandardResearcher(_RESEARCH), draft)

    # Act
    result = await tool.ainvoke({})

    # Assert — the findings are recorded on the brief (the whole point: downstream stages read it),
    # the original brief fields survive the copy, and the stage was emitted.
    assert draft.brief.research == _RESEARCH
    assert draft.brief.subject == "English proficiency"  # the model_copy preserved the rest
    assert ProgressStage.STANDARD_RESEARCHED in draft.progress.stages  # type: ignore[attr-defined]
    # The returned dict mirrors the recorded research as camelCase JSON for the timeline.
    assert result["status"] == "complete"
    assert result["sources"][0]["trustTier"] == "official"


async def test_research_standard_degrades_to_unavailable_without_a_brief() -> None:
    # Arrange — interpretation was skipped, so there is no standard to research.
    draft = CourseDraft(topic="anything", course_id="c", run_id="r")
    draft.progress = _RecordingProgress()  # type: ignore[assignment]

    # A researcher that would explode if called, proving the no-brief path never invokes it.
    class _ExplodingResearcher:
        async def research(self, brief: CourseBrief) -> StandardResearch:
            raise AssertionError("researcher must not run without a brief")

    tool = make_research_standard_tool(_ExplodingResearcher(), draft)

    # Act
    result = await tool.ainvoke({})

    # Assert — honest degradation: UNAVAILABLE, no sources, the stage still emits, nothing crashes.
    assert result["status"] == "unavailable"
    assert result["sources"] == []
    assert draft.brief is None  # nothing fabricated onto a missing brief
    assert ProgressStage.STANDARD_RESEARCHED in draft.progress.stages  # type: ignore[attr-defined]


# Variant coverage: every research outcome the stage can produce — grounded, thin, and unreachable —
# records onto the brief, emits the stage, and returns the right status, with the source/competency
# shapes the schema invariant allows (COMPLETE cites a source; UNAVAILABLE carries none).
_OUTCOMES = [
    StandardResearch(
        status=ResearchStatus.COMPLETE,
        competencies=["hear implied intent"],
        sources=[ResearchSource(url="https://www.canada.ca/clb", trust_tier=TrustTier.OFFICIAL)],
    ),
    StandardResearch(
        status=ResearchStatus.PARTIAL,
        competencies=[],
        sources=[ResearchSource(url="https://uni.edu/clb", trust_tier=TrustTier.REPUTABLE)],
    ),
    StandardResearch(status=ResearchStatus.UNAVAILABLE),
]


@pytest.mark.parametrize("research", _OUTCOMES, ids=lambda r: r.status.value)
async def test_research_standard_records_and_emits_every_outcome(
    research: StandardResearch,
) -> None:
    # Arrange — an interpreted brief; the researcher returns the parametrized outcome.
    draft = CourseDraft(topic="English", course_id="c", run_id="r")
    draft.brief = CourseBrief(subject="English", goal="reach CLB 10", target_level=Level.ADVANCED)
    draft.progress = _RecordingProgress()  # type: ignore[assignment]
    tool = make_research_standard_tool(StubStandardResearcher(research), draft)

    # Act
    result = await tool.ainvoke({})

    # Assert — each outcome is recorded on the brief, round-trips to camelCase JSON (status,
    # competencies, and the vetted sources), and emits the stage exactly once.
    assert draft.brief.research == research
    expected = research.model_dump(mode="json", by_alias=True)
    assert result["status"] == expected["status"]
    assert result["competencies"] == expected["competencies"]
    assert result["sources"] == expected["sources"]
    assert draft.progress.stages == [ProgressStage.STANDARD_RESEARCHED]  # type: ignore[attr-defined]
