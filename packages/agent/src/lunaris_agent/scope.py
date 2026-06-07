"""The scope-realism estimator (CQ Phase 3.1): an honest at-a-glance framing of a course.

Computes a ``CourseScope`` — effort/timeline + what the course does and does not get you — from the
brief's abstractions (goal_type, gap magnitude, target level) and the module count, never from a
topic, so the framing is generic across any subject (the Genericity Rule). Pure + deterministic; the
finalize tool applies it, and an optional key-gated polish step may refine the wording of the
does/doesn't lines without changing the effort facts.
"""

from lunaris_runtime.schema import (
    Course,
    CourseBrief,
    CourseScope,
    GapMagnitude,
    GoalType,
    Level,
    TargetStandard,
)

# Hours of study a module of a given target level tends to take (low, high). A denser, higher-level
# module is more work than a novice one. NOT_APPLICABLE (no proficiency ladder) sizes to the middle.
_LEVEL_HOURS_PER_MODULE: dict[Level, tuple[int, int]] = {
    Level.NOVICE: (2, 3),
    Level.INTERMEDIATE: (3, 5),
    Level.ADVANCED: (4, 6),
    Level.EXPERT: (5, 8),
    Level.NOT_APPLICABLE: (3, 5),
}

# A larger entry->target gap is honestly more work for the same modules (more to bridge per KC).
_MAGNITUDE_MULTIPLIER: dict[GapMagnitude, float] = {
    GapMagnitude.SMALL: 0.8,
    GapMagnitude.MODERATE: 1.0,
    GapMagnitude.LARGE: 1.3,
}

# Self-paced study cadence: an engaged learner puts in ~5 h/week (fewer weeks), a lighter one ~3
# h/week (more weeks). The two cadences become the ends of the weeks range.
_WEEKLY_HOURS_ENGAGED: int = 5
_WEEKLY_HOURS_LIGHT: int = 3

# Human words for the target level; NOT_APPLICABLE carries no meaningful proficiency phrase.
_LEVEL_WORD: dict[Level, str] = {
    Level.NOVICE: "beginner",
    Level.INTERMEDIATE: "intermediate",
    Level.ADVANCED: "advanced",
    Level.EXPERT: "expert",
    Level.NOT_APPLICABLE: "",
}


def _effort_band(*, modules: int, level: Level, magnitude: GapMagnitude) -> tuple[int, int]:
    """The (low, high) study-hours band. Pure; monotonic in modules, level, and gap magnitude."""
    module_count = max(modules, 1)
    low_per, high_per = _LEVEL_HOURS_PER_MODULE[level]
    multiplier = _MAGNITUDE_MULTIPLIER[magnitude]
    low_hours = max(1, round(module_count * low_per * multiplier))
    high_hours = max(low_hours + 1, round(module_count * high_per * multiplier))
    return low_hours, high_hours


def _effort_phrase(low_hours: int, high_hours: int) -> str:
    """A human effort/timeline band: a weeks range at a self-paced cadence, plus the raw hours."""
    weeks_low = max(1, round(low_hours / _WEEKLY_HOURS_ENGAGED))
    weeks_high = max(weeks_low + 1, round(high_hours / _WEEKLY_HOURS_LIGHT))
    return (
        f"About {weeks_low}-{weeks_high} weeks of self-paced study "
        f"(~{low_hours}-{high_hours} hours)."
    )


def _level_phrase(level: Level) -> str:
    """`` at the intermediate level`` — or empty for a goal with no proficiency ladder."""
    word = _LEVEL_WORD[level]
    return f" at the {word} level" if word else ""


def _standard_or_subject(brief: CourseBrief | None, course: Course) -> str:
    """The named standard when the goal targets one, else the brief's subject, else the topic."""
    standard: TargetStandard | None = brief.target_standard if brief else None
    if standard is not None and standard.name:
        return standard.name
    if brief is not None and brief.subject:
        return brief.subject
    return course.topic


def _delivers(goal_type: GoalType, *, subject: str, level: Level, modules: int) -> list[str]:
    """What the course DOES get you — a goal-type framing line + the module-count line."""
    level_phrase = _level_phrase(level)
    framing = {
        GoalType.KNOWLEDGE: (
            f"A structured understanding of {subject}{level_phrase}, built backward from your goal."
        ),
        GoalType.SKILL: (
            f"A practised ability to apply {subject}{level_phrase}, built from worked examples "
            "into your own practice."
        ),
        GoalType.CREDENTIAL: (
            f"The competency framework behind {subject}{level_phrase}, mapped to the modules you "
            "work through in order."
        ),
        GoalType.BEHAVIOR: (
            f"Routines and strategies for sustaining {subject} as an ongoing "
            f"practice{level_phrase}."
        ),
    }[goal_type]
    module_count = max(modules, 1)
    plural = "s" if module_count != 1 else ""
    modules_line = (
        f"{module_count} module{plural} sequenced by prerequisite, each grounded against "
        "verified sources where the corpus allows."
    )
    return [framing, modules_line]


def _excludes(goal_type: GoalType, *, award_name: str, level: Level) -> list[str]:
    """What the course does NOT get you — the goal-type-inherent limit + an optional level limit.

    ``award_name`` is the credential body's name when the goal targets a standard, else the fallback
    subject; only the CREDENTIAL branch reads it (to disclaim affiliation with the awarding body).
    """
    framing = {
        GoalType.KNOWLEDGE: (
            "It will not certify you or formally assess your mastery — it is a learning "
            "resource, not a credential."
        ),
        GoalType.SKILL: (
            "It will not build the skill for you: the capability comes from doing the "
            "practice, not reading about it."
        ),
        GoalType.CREDENTIAL: (
            "It will not guarantee a passing score and is not affiliated with the body that "
            f"awards {award_name}."
        ),
        GoalType.BEHAVIOR: (
            "It will not sustain the habit on your behalf — the change comes from your ongoing "
            "practice over time."
        ),
    }[goal_type]
    lines = [framing]
    if level in (Level.ADVANCED, Level.EXPERT):
        lines.append(
            "It does not re-teach the foundations below your target level — it assumes the "
            "prerequisites below."
        )
    return lines


def estimate_scope(course: Course, brief: CourseBrief | None) -> CourseScope:
    """The scope-realism band for a finalized course. Deterministic; topic-blind.

    Reads the brief's abstractions (goal_type, gap magnitude, target level) — not the topic — so the
    framing reads sensibly for any subject. With no brief (the stub/legacy direct-assembly path) it
    falls back to the course's own ``goal_type`` and topic, sizing effort at a moderate gap.
    """
    goal_type = brief.goal_type if brief else course.goal_type
    level = brief.target_level if brief else Level.NOT_APPLICABLE
    magnitude = brief.gap.magnitude if brief else GapMagnitude.MODERATE
    modules = len(course.modules)
    subject = brief.subject if brief and brief.subject else course.topic

    low_hours, high_hours = _effort_band(modules=modules, level=level, magnitude=magnitude)
    return CourseScope(
        effort=_effort_phrase(low_hours, high_hours),
        delivers=_delivers(goal_type, subject=subject, level=level, modules=modules),
        excludes=_excludes(goal_type, award_name=_standard_or_subject(brief, course), level=level),
    )
