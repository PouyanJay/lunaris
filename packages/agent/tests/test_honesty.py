"""CQ Phase 1.6 — the honesty gate: a research-needing goal that couldn't be grounded is labeled
+ withheld, never shipped as an authoritative guide to a standard it didn't research."""

from lunaris_agent.honesty import assess_grounding_honesty
from lunaris_runtime.schema import (
    CourseBrief,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
    TargetStandard,
)


def _needs_research_brief(research: StandardResearch | None) -> CourseBrief:
    return CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        needs_research=True,
        target_standard=TargetStandard(name="CLB 10"),
        research=research,
    )


def test_unavailable_research_is_caveated_and_withheld() -> None:
    # Arrange — a research-needing goal whose research came back UNAVAILABLE.
    brief = _needs_research_brief(StandardResearch(status=ResearchStatus.UNAVAILABLE))

    # Act
    honesty = assess_grounding_honesty(brief)

    # Assert — a clear caveat naming the standard, and the course is withheld from publication.
    assert "CLB 10" in honesty.caveat
    assert "general introduction" in honesty.caveat
    assert honesty.needs_review is True


def test_missing_research_is_treated_as_unavailable() -> None:
    # Arrange / Act — a needs_research goal whose research was never recorded (None).
    honesty = assess_grounding_honesty(_needs_research_brief(None))

    # Assert — same as UNAVAILABLE: caveated + withheld.
    assert honesty.caveat
    assert honesty.needs_review is True


def test_partial_research_is_caveated_but_may_publish() -> None:
    # Arrange — some sources reached but grounding was thin.
    brief = _needs_research_brief(
        StandardResearch(
            status=ResearchStatus.PARTIAL,
            sources=[ResearchSource(url="https://www.canada.ca/clb-10")],
        )
    )

    # Act
    honesty = assess_grounding_honesty(brief)

    # Assert — a softer caveat, but not withheld (it IS partially grounded).
    assert "partially grounded" in honesty.caveat
    assert honesty.needs_review is False


def test_complete_research_has_no_caveat() -> None:
    # Arrange — fully grounded research (COMPLETE requires a cited source).
    brief = _needs_research_brief(
        StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=["infer implied intent"],
            sources=[ResearchSource(url="https://www.canada.ca/clb-10")],
        )
    )

    # Act
    honesty = assess_grounding_honesty(brief)

    # Assert
    assert honesty.caveat == ""
    assert honesty.needs_review is False


def test_a_goal_that_does_not_need_research_is_never_gated() -> None:
    # A knowledge goal with no external standard has nothing to be dishonest about, even with no
    # research — the gate must not flag every keyless build.
    brief = CourseBrief(subject="Houseplants", goal="keep houseplants alive", needs_research=False)

    honesty = assess_grounding_honesty(brief)

    assert honesty.caveat == ""
    assert honesty.needs_review is False


def test_no_brief_is_not_gated() -> None:
    # The stub/legacy path finalizes with no brief — the gate must be a no-op, not crash.
    honesty = assess_grounding_honesty(None)

    assert honesty.caveat == ""
    assert honesty.needs_review is False
