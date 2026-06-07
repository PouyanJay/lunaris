"""CQ Phase 1 — the Genericity Rule (binding): every Phase-1 policy keys off the brief's
ABSTRACTIONS (goal_type / target_level / gap / needs_research), never the topic.

The journey's final task parametrizes the Phase-1 behaviors over ≥3 different goal types / domains
and asserts they hold for all — so no CLB/English-specific logic can have leaked in. If a fix only
worked for one topic, one of these cases would diverge.
"""

import pytest
from lunaris_agent.honesty import assess_grounding_honesty
from lunaris_grounding import research_budget_for_brief
from lunaris_runtime.schema import (
    CourseBrief,
    Gap,
    GapMagnitude,
    GoalType,
    Level,
    ResearchStatus,
    StandardResearch,
    TargetStandard,
)

# Four genuinely different goal types / domains (plan §Genericity Rule). Each is a DEMANDING goal
# (high level, real gap) so the depth policy and honesty gate are exercised at their strong end.
_AWS = CourseBrief(
    subject="AWS cloud architecture",
    goal="Pass the AWS Certified Solutions Architect exam",
    goal_type=GoalType.CREDENTIAL,
    target_level=Level.INTERMEDIATE,
    gap=Gap(entry_level=Level.NOVICE, magnitude=GapMagnitude.LARGE),
    needs_research=True,
    target_standard=TargetStandard(name="AWS Certified Solutions Architect"),
)
_CLB = CourseBrief(
    subject="English language proficiency",
    goal="reach CLB 10 across all four skills",
    goal_type=GoalType.CREDENTIAL,
    target_level=Level.ADVANCED,
    gap=Gap(entry_level=Level.ADVANCED, magnitude=GapMagnitude.MODERATE),
    needs_research=True,
    target_standard=TargetStandard(name="CLB 10"),
)
_ABRSM = CourseBrief(
    subject="Classical piano performance",
    goal="reach ABRSM Grade 8 piano",
    goal_type=GoalType.SKILL,
    target_level=Level.ADVANCED,
    gap=Gap(entry_level=Level.INTERMEDIATE, magnitude=GapMagnitude.LARGE),
    needs_research=True,
    target_standard=TargetStandard(name="ABRSM Grade 8 Piano"),
)
_RUST = CourseBrief(
    subject="The Rust programming language",
    goal="write idiomatic Rust",
    goal_type=GoalType.SKILL,
    target_level=Level.ADVANCED,
    gap=Gap(entry_level=Level.INTERMEDIATE, magnitude=GapMagnitude.MODERATE),
    needs_research=False,  # a skill with no external standard to research
)
_HABIT = CourseBrief(
    subject="Deliberate-practice routines",
    goal="build a daily deliberate-practice habit",
    goal_type=GoalType.BEHAVIOR,
    target_level=Level.ADVANCED,
    gap=Gap(entry_level=Level.NOVICE, magnitude=GapMagnitude.LARGE),
    needs_research=False,  # a behavior-change goal with no external standard
)

# Four goal TYPES across five domains: credential (AWS, CLB), skill (ABRSM, Rust), behavior (habit).
# Rust + habit are in the depth sweep to prove needs_research=False does NOT suppress the budget.
_DEMANDING = [_AWS, _CLB, _ABRSM, _RUST, _HABIT]
_NEEDS_RESEARCH = [_AWS, _CLB, _ABRSM]


@pytest.mark.parametrize("brief", _DEMANDING, ids=lambda b: f"{b.goal_type.value}:{b.subject}")
def test_depth_policy_grants_multi_round_research_for_every_demanding_goal(
    brief: CourseBrief,
) -> None:
    # Act — the depth policy earns a deepening round for any demanding goal (high level, real gap),
    # across all goal types and topics (English / AWS / piano / Rust / habit).
    budget = research_budget_for_brief(brief)

    # Assert
    assert budget.max_rounds >= 2
    assert budget.max_searches > 3  # above the casual floor


def test_depth_policy_is_blind_to_the_topic() -> None:
    # Arrange — two briefs with IDENTICAL abstractions but totally different topics.
    shape = {
        "goal_type": GoalType.CREDENTIAL,
        "target_level": Level.EXPERT,
        "gap": Gap(entry_level=Level.NOVICE, magnitude=GapMagnitude.LARGE),
    }
    one = CourseBrief(subject="Medieval history", goal="pass exam A", **shape)
    two = CourseBrief(subject="Quantum chemistry", goal="pass exam B", **shape)

    # Act / Assert — same abstractions → same budget; the policy never reads the subject/goal text
    # (the Genericity Rule made concrete).
    assert research_budget_for_brief(one) == research_budget_for_brief(two)


@pytest.mark.parametrize(
    "brief", _NEEDS_RESEARCH, ids=lambda b: b.target_standard.name if b.target_standard else "?"
)
def test_honesty_gate_fires_for_every_ungrounded_credential_or_exam(brief: CourseBrief) -> None:
    # Arrange — the same goal with its research come back UNAVAILABLE.
    ungrounded = brief.model_copy(
        update={"research": StandardResearch(status=ResearchStatus.UNAVAILABLE)}
    )
    standard = brief.target_standard.name if brief.target_standard else ""

    # Act
    honesty = assess_grounding_honesty(ungrounded)

    # Assert — caveated + withheld for ANY standard, naming THAT standard (keys off needs_research,
    # not "is this CLB").
    assert honesty.needs_review is True
    assert standard and standard in honesty.caveat


def test_honesty_gate_does_not_fire_for_a_non_research_skill() -> None:
    # The idiomatic-Rust skill has no external standard → the gate must not flag it, proving it keys
    # off the abstraction (needs_research), not the presence of content.
    honesty = assess_grounding_honesty(_RUST)

    assert honesty.caveat == ""
    assert honesty.needs_review is False
