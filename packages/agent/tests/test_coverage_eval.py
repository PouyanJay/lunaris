"""CQ Phase 4.2 — the coverage-judge eval (live, key-gated).

The headline the deterministic check can't prove: the LLM judge catches a competency that is
*structurally* present (a module is tagged with it) but not *materially* built — only mentioned,
with no real teaching or practice. The deterministic critic would call that covered; the judge must
not. And a module that genuinely teaches + practises its competency must stay clean (no over-flag).
Proven for more than one goal type (the Genericity Rule). Deselected by default; run with a live
Anthropic key via ``-m eval``. The offline ``test_coverage_critic`` suite proves the parse +
fallback with a fake model; this proves the judgement itself against the live model.
"""

import os

import pytest
from lunaris_agent.coverage_critic import ClaudeCoverageCritic
from lunaris_runtime.schema import (
    Course,
    CourseBrief,
    GoalType,
    Lesson,
    Level,
    MerrillSegments,
    Module,
    ResearchSource,
    ResearchStatus,
    Segment,
    StandardResearch,
)

pytestmark = pytest.mark.eval

# Worker tier (cheap + fast): flagging an obviously-unbuilt competency is a light judgement.
_DEFAULT_WORKER = "claude-haiku-4-5-20251001"

# Two goal types over unrelated domains — the judge's "built vs merely mentioned" call must hold
# regardless of the goal kind or topic (the Genericity Rule).
_CASES = [
    (GoalType.CREDENTIAL, "AWS Solutions Architect", "design a fault-tolerant multi-AZ VPC"),
    (GoalType.SKILL, "CLB 10 English", "infer implied intent in extended speech"),
]


def _segment(prose: str) -> Segment:
    return Segment(prose=prose)


def _lesson(*, activate: str, demonstrate: str, apply: str, integrate: str) -> Lesson:
    return Lesson(
        id="l0",
        segments=MerrillSegments(
            activate=_segment(activate),
            demonstrate=_segment(demonstrate),
            apply=_segment(apply),
            integrate=_segment(integrate),
        ),
    )


def _brief(goal_type: GoalType, subject: str, competency: str) -> CourseBrief:
    return CourseBrief(
        subject=subject,
        goal=f"reach {subject}",
        goal_type=goal_type,
        target_level=Level.ADVANCED,
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=[competency],
            sources=[ResearchSource(url="https://example.org/standard")],
        ),
    )


def _critic() -> ClaudeCoverageCritic:
    return ClaudeCoverageCritic(os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER))


@pytest.mark.parametrize(("goal_type", "subject", "competency"), _CASES)
async def test_live_judge_flags_a_merely_mentioned_competency(
    goal_type: GoalType, subject: str, competency: str
) -> None:
    # Arrange — a module TAGGED with the competency (so the deterministic check would pass) whose
    # lesson only mentions it and gives no practice. The live judge must see through the label.
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY unset; the coverage-judge eval needs a live model")
    brief = _brief(goal_type, subject, competency)
    thin = _lesson(
        activate="",
        demonstrate=f"We will look at {competency} later in the program.",
        apply="",
        integrate="",
    )
    course = Course(
        id="c",
        topic=subject,
        goal_type=goal_type,
        modules=[Module(id="m0", title="Placeholder", competency=competency, lessons=[thin])],
    )

    # Act
    report = await _critic().review(course, brief=brief)

    # Assert — the merely-mentioned competency is flagged as not materially built.
    assert competency in [gap.competency for gap in report.gaps]


@pytest.mark.parametrize(("goal_type", "subject", "competency"), _CASES)
async def test_live_judge_keeps_a_genuinely_built_competency_clean(
    goal_type: GoalType, subject: str, competency: str
) -> None:
    # Arrange — a module that actually teaches the competency (a worked example) AND practises it
    # (an apply task) AND transfers it. The judge must not over-flag a real build.
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY unset; the coverage-judge eval needs a live model")
    brief = _brief(goal_type, subject, competency)
    built = _lesson(
        activate=f"Recall a situation that calls for {competency}.",
        demonstrate=(
            f"Worked example of {competency}: a step-by-step walkthrough with the key decisions "
            "explained and a concrete result."
        ),
        apply=f"Now practise {competency} yourself on this scenario, then check your work.",
        integrate=f"Apply {competency} to your own context this week.",
    )
    course = Course(
        id="c",
        topic=subject,
        goal_type=goal_type,
        modules=[Module(id="m0", title="Built", competency=competency, lessons=[built])],
    )

    # Act
    report = await _critic().review(course, brief=brief)

    # Assert — a genuinely built competency is not flagged.
    assert report.is_clean
