"""CQ Phase 3.1 — the deterministic scope-realism estimator.

The band is computed from the brief's abstractions (goal_type, gap magnitude, target level) and the
module count — never from the topic — so it must read sensibly for any subject. These tests pin the
goal-type-specific framing, the honest exclusions, the effort scaling, and the no-brief fallback.
"""

import re

import pytest

# ``_effort_band`` is a private pure helper deliberately tested in isolation: its monotonicity is
# a mathematical contract that is awkward to observe through the public ``estimate_scope`` string
# without fragile parsing. ``estimate_scope`` is also exercised directly for user-facing content.
from lunaris_agent.scope import _effort_band, estimate_scope
from lunaris_runtime.schema import (
    Course,
    CourseBrief,
    Gap,
    GapMagnitude,
    GoalType,
    Level,
    Module,
    TargetStandard,
)


def _course(*, modules: int = 4, goal_type: GoalType = GoalType.KNOWLEDGE) -> Course:
    """A finalized course shell with ``modules`` modules — enough to size the effort band."""
    mods = [Module(id=f"k{i}", title=f"Concept {i}", kcs=[f"k{i}"]) for i in range(modules)]
    return Course(id="c", topic="anything at all", goal_type=goal_type, modules=mods)


def _brief(
    *,
    goal_type: GoalType = GoalType.KNOWLEDGE,
    magnitude: GapMagnitude = GapMagnitude.MODERATE,
    target_level: Level = Level.INTERMEDIATE,
    standard: TargetStandard | None = None,
) -> CourseBrief:
    return CourseBrief(
        subject="the subject",
        goal="the goal",
        goal_type=goal_type,
        target_level=target_level,
        target_standard=standard,
        gap=Gap(magnitude=magnitude),
    )


def test_effort_scales_with_gap_magnitude() -> None:
    # Same modules + level, a LARGER gap is honestly more work than a SMALL one (monotonic).
    small_low, small_high = _effort_band(
        modules=4, level=Level.INTERMEDIATE, magnitude=GapMagnitude.SMALL
    )
    large_low, large_high = _effort_band(
        modules=4, level=Level.INTERMEDIATE, magnitude=GapMagnitude.LARGE
    )
    assert large_low >= small_low
    assert large_high > small_high


def test_effort_scales_with_module_count() -> None:
    # More modules = more hours (a bottom-up signal), holding level + magnitude fixed — both bounds.
    few = _effort_band(modules=2, level=Level.INTERMEDIATE, magnitude=GapMagnitude.MODERATE)
    many = _effort_band(modules=8, level=Level.INTERMEDIATE, magnitude=GapMagnitude.MODERATE)
    assert many[0] > few[0]
    assert many[1] > few[1]


def test_effort_scales_with_target_level() -> None:
    # A higher target level is honestly denser work for the same modules + gap (monotonic).
    novice = _effort_band(modules=4, level=Level.NOVICE, magnitude=GapMagnitude.MODERATE)
    expert = _effort_band(modules=4, level=Level.EXPERT, magnitude=GapMagnitude.MODERATE)
    assert expert[0] > novice[0]
    assert expert[1] > novice[1]


def test_effort_band_is_a_valid_ascending_range() -> None:
    low, high = _effort_band(modules=4, level=Level.NOVICE, magnitude=GapMagnitude.MODERATE)
    assert 0 < low < high


def test_effort_string_carries_a_weeks_range_and_raw_hours() -> None:
    # Pin the real contract (not the T0 placeholder): a numeric weeks range AND a raw-hours band.
    scope = estimate_scope(_course(), _brief())
    assert re.search(r"\d+-\d+ weeks", scope.effort), f"no weeks range in {scope.effort!r}"
    assert re.search(r"~\d+-\d+ hours", scope.effort), f"no raw-hours band in {scope.effort!r}"


def test_credential_goal_excludes_a_passing_guarantee() -> None:
    # A credential course must never imply it guarantees the exam result.
    scope = estimate_scope(
        _course(goal_type=GoalType.CREDENTIAL),
        _brief(goal_type=GoalType.CREDENTIAL, standard=TargetStandard(name="AWS SA-C03")),
    )
    blob = " ".join(scope.excludes).lower()
    assert "guarantee" in blob
    assert "AWS SA-C03" in " ".join(scope.excludes)


def test_skill_goal_excludes_replacing_hands_on_practice() -> None:
    scope = estimate_scope(_course(goal_type=GoalType.SKILL), _brief(goal_type=GoalType.SKILL))
    blob = " ".join(scope.excludes).lower()
    # Distinctive to SKILL: the capability comes from doing, not *reading*.
    assert "practice" in blob
    assert "reading" in blob


def test_knowledge_goal_excludes_certification() -> None:
    scope = estimate_scope(
        _course(goal_type=GoalType.KNOWLEDGE), _brief(goal_type=GoalType.KNOWLEDGE)
    )
    blob = " ".join(scope.excludes).lower()
    assert "certif" in blob or "credential" in blob or "assess" in blob


def test_behavior_goal_excludes_sustaining_the_habit_for_you() -> None:
    scope = estimate_scope(
        _course(goal_type=GoalType.BEHAVIOR), _brief(goal_type=GoalType.BEHAVIOR)
    )
    blob = " ".join(scope.excludes).lower()
    # Distinctive to BEHAVIOR: it won't sustain the *habit* for you over time.
    assert "habit" in blob
    assert "ongoing" in blob


def test_delivers_names_the_target_level() -> None:
    scope = estimate_scope(_course(), _brief(target_level=Level.ADVANCED))
    assert "advanced" in " ".join(scope.delivers).lower()


def test_delivers_counts_the_modules() -> None:
    scope = estimate_scope(_course(modules=6), _brief())
    assert "6" in " ".join(scope.delivers)


@pytest.mark.parametrize("goal_type", list(GoalType))
def test_every_goal_type_yields_a_populated_band(goal_type: GoalType) -> None:
    # The Genericity Rule: every goal kind produces a non-empty, topic-blind band. delivers always
    # carries the framing + module-count lines, so a stripped line is a regression.
    scope = estimate_scope(_course(goal_type=goal_type), _brief(goal_type=goal_type))
    assert scope.effort
    assert len(scope.delivers) >= 2
    assert scope.excludes


def test_zero_module_course_produces_a_valid_band() -> None:
    # A stub/degenerate course with no modules must still yield a sane band (the safe_modules=1
    # clamp), never crash or emit "0 modules" — the polish layer (T2) consumes this result.
    scope = estimate_scope(_course(modules=0), _brief())
    assert re.search(r"\d+-\d+ weeks", scope.effort)
    assert "1 module " in " ".join(scope.delivers)  # singular, clamped — not "0 modules"
    assert scope.excludes


def test_no_brief_falls_back_to_the_course_goal_type_without_crashing() -> None:
    # The stub/legacy direct-assembly path finalizes with no brief — the estimator must still
    # produce a band, keyed off the course's own goal_type, never raise.
    scope = estimate_scope(_course(goal_type=GoalType.SKILL), None)
    assert scope.effort and scope.delivers and scope.excludes
    assert "practice" in " ".join(scope.excludes).lower()


def test_not_applicable_level_omits_a_level_phrase() -> None:
    # A goal with no proficiency ladder must not read "at the n/a level".
    scope = estimate_scope(_course(), _brief(target_level=Level.NOT_APPLICABLE))
    assert "n/a" not in " ".join(scope.delivers).lower()
