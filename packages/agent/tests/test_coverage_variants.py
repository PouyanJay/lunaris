"""CQ Phase 4.2 — the coverage gate holds across goal types (the Genericity Rule).

The final-task variant matrix: the coverage critic keys off the brief's researched competencies and
the modules' competency tags — never the topic — so it must flag an unbuilt competency identically
for a credential, a skill, or a behavior goal, across unrelated domains. Proven deterministically
here (the live LLM judge is proven by ``test_coverage_eval``). Includes the backward-compat no-op:
a pre-P4 course (no research) is never gated.
"""

import pytest
from lunaris_agent.coverage_critic import DeterministicCoverageCritic
from lunaris_runtime.schema import (
    Course,
    CourseBrief,
    GoalType,
    Level,
    Module,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
)

# (goal_type, subject, one competency, a second competency) — all four goal types over unrelated
# domains (AWS-SA / DB internals / CLB / ABRSM / Rust / habit), topic-blind by construction. Each
# test decides which of the two competencies a module builds.
_VARIANTS = [
    pytest.param(
        GoalType.CREDENTIAL,
        "AWS Solutions Architect",
        "design a multi-AZ VPC",
        "right-size EC2 instances for cost",
        id="aws-credential",
    ),
    pytest.param(
        GoalType.KNOWLEDGE,
        "relational database internals",
        "explain MVCC snapshot isolation",
        "read a query execution plan",
        id="db-knowledge",
    ),
    pytest.param(
        GoalType.SKILL,
        "CLB 10 English",
        "hear implied intent in speech",
        "adapt register live in speech",
        id="clb-skill",
    ),
    pytest.param(
        GoalType.SKILL,
        "ABRSM Grade 8 piano",
        "voice a four-part chord",
        "pedal legato cleanly",
        id="abrsm-skill",
    ),
    pytest.param(
        GoalType.SKILL,
        "idiomatic Rust",
        "model ownership with borrows",
        "handle errors with Result",
        id="rust-skill",
    ),
    pytest.param(
        GoalType.BEHAVIOR,
        "a daily writing habit",
        "set an implementation intention",
        "track a streak honestly",
        id="habit-behavior",
    ),
]


def _brief(goal_type: GoalType, subject: str, competencies: list[str]) -> CourseBrief:
    return CourseBrief(
        subject=subject,
        goal=f"reach {subject}",
        goal_type=goal_type,
        target_level=Level.ADVANCED,
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=competencies,
            sources=[ResearchSource(url="https://example.org/standard")],
        ),
    )


def _critic() -> DeterministicCoverageCritic:
    return DeterministicCoverageCritic()


@pytest.mark.parametrize(("goal_type", "subject", "built", "other"), _VARIANTS)
async def test_coverage_flags_the_unbuilt_competency_for_every_goal_type(
    goal_type: GoalType, subject: str, built: str, other: str
) -> None:
    # Arrange — one module tagged with the built competency; the other module tagged with nothing,
    # so the second promised competency is unbuilt. Topic varies; the gate's logic must not.
    brief = _brief(goal_type, subject, [built, other])
    course = Course(
        id="c",
        topic=subject,
        goal_type=goal_type,
        modules=[
            Module(id="m0", title="Built", competency=built),
            Module(id="m1", title="Other", competency=None),
        ],
    )

    # Act
    report = await _critic().review(course, brief=brief)

    # Assert — exactly the unbuilt competency is flagged, identically across goal types/domains.
    assert [gap.competency for gap in report.gaps] == [other]


@pytest.mark.parametrize(("goal_type", "subject", "built", "other"), _VARIANTS)
async def test_coverage_is_clean_when_every_competency_is_built_for_every_goal_type(
    goal_type: GoalType, subject: str, built: str, other: str
) -> None:
    # Arrange — both promised competencies are tagged to a module.
    brief = _brief(goal_type, subject, [built, other])
    course = Course(
        id="c",
        topic=subject,
        goal_type=goal_type,
        modules=[
            Module(id="m0", title="Built", competency=built),
            Module(id="m1", title="Also built", competency=other),
        ],
    )

    # Act
    report = await _critic().review(course, brief=brief)

    # Assert — fully covered, for every goal type.
    assert report.is_clean


@pytest.mark.parametrize(("goal_type", "subject", "built", "other"), _VARIANTS)
async def test_coverage_is_a_noop_for_a_pre_p4_course_for_every_goal_type(
    goal_type: GoalType, subject: str, built: str, other: str
) -> None:
    # Backward-compat: a course built before P4 has no researched competencies (and untagged
    # modules), so the coverage gate is a no-op — it never flags or withholds a legacy course.
    # Arrange
    brief = CourseBrief(subject=subject, goal=f"reach {subject}", goal_type=goal_type)
    course = Course(
        id="c",
        topic=subject,
        goal_type=goal_type,
        modules=[Module(id="m0", title="Legacy", competency=None)],
    )

    # Act
    report = await _critic().review(course, brief=brief)

    # Assert
    assert report.is_clean
