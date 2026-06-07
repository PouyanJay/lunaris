"""Derive the interpret clarifier's confirm questions from an inferred :class:`CourseBrief` (P7.5).

Pure + deterministic: the options come from the backend enums and the Recommended pre-pick is the
interpreter's guess, so the zero-friction path is a single confirm. Answers map back onto a
:class:`Clarification` by question id (goal/level/knowledge/background/detail/language). They are
folded onto the brief by ``apply_clarification``. The enum questions are closed (bands exhaustive);
open input is captured by the free-TEXT knowledge/background questions.
"""

from enum import StrEnum

from lunaris_runtime.schema import (
    Clarifier,
    ClarifierKind,
    ClarifierOption,
    ClarifierQuestion,
    CourseBrief,
    DetailDepth,
    GoalType,
    LanguageStyle,
    Level,
)

# What KIND of outcome the learner wants (CQ Phase 1) — drives the deliverable shape + research
# depth, so it's the first thing the learner confirms.
_GOAL_TYPE_LABELS: dict[GoalType, str] = {
    GoalType.KNOWLEDGE: "Understand a topic",
    GoalType.SKILL: "Build a skill",
    GoalType.CREDENTIAL: "Pass an exam / get certified",
    GoalType.BEHAVIOR: "Change a habit or practice",
}

# Human labels for the enum choices — the web renders these, not the raw enum values. Kept here so
# the labels live with the question derivation (one source of truth), ordered as the UI shows them.
_LEVEL_LABELS: dict[Level, str] = {
    Level.NOVICE: "Beginner",
    Level.INTERMEDIATE: "Intermediate",
    Level.ADVANCED: "Advanced",
    Level.EXPERT: "Expert",
    Level.NOT_APPLICABLE: "Not sure / general",
}
_DETAIL_LABELS: dict[DetailDepth, str] = {
    DetailDepth.CONCISE: "Concise",
    DetailDepth.BALANCED: "Balanced",
    DetailDepth.IN_DEPTH: "In-depth",
}
_LANGUAGE_LABELS: dict[LanguageStyle, str] = {
    LanguageStyle.SIMPLE: "Simple & plain",
    LanguageStyle.BALANCED: "Balanced",
    LanguageStyle.SOPHISTICATED: "Sophisticated",
    LanguageStyle.SCIENTIFIC: "Technical / scientific",
}

_KNOWLEDGE_HINT = "e.g. the basics, but not the advanced parts"
_BACKGROUND_HINT = "e.g. a backend engineer prepping for a system-design interview"


def build_clarifier(brief: CourseBrief) -> Clarifier:
    """Build the confirm questions for ``brief``, each pre-picking the interpreter's guess."""
    return Clarifier(
        questions=[
            _choice(
                "goal", "What kind of outcome do you want?", _GOAL_TYPE_LABELS, brief.goal_type
            ),
            _choice(
                "level", "What's your current level with this?", _LEVEL_LABELS, brief.target_level
            ),
            ClarifierQuestion(
                id="knowledge",
                prompt="What are you already comfortable with? We'll skip it.",
                kind=ClarifierKind.TEXT,
                placeholder=brief.assumed_prior or _KNOWLEDGE_HINT,
            ),
            ClarifierQuestion(
                id="background",
                prompt="What's your background, and why this goal?",
                kind=ClarifierKind.TEXT,
                placeholder=_BACKGROUND_HINT,
            ),
            _choice(
                "detail",
                "How much depth do you want?",
                _DETAIL_LABELS,
                brief.preferences.detail_depth,
            ),
            _choice(
                "language",
                "What writing style fits you best?",
                _LANGUAGE_LABELS,
                brief.preferences.language_style,
            ),
        ]
    )


def _choice[E: StrEnum](
    qid: str, prompt: str, labels: dict[E, str], recommended: E
) -> ClarifierQuestion:
    """A closed CHOICE over ``labels`` with the inferred ``recommended`` value pre-picked.

    ``E`` (the enum the choice is built from) ties the option keys to the recommended value, so a
    mismatched recommended type is a type error at the call site.
    """
    options = [
        ClarifierOption(value=value.value, label=label, recommended=value == recommended)
        for value, label in labels.items()
    ]
    return ClarifierQuestion(id=qid, prompt=prompt, kind=ClarifierKind.CHOICE, options=options)
