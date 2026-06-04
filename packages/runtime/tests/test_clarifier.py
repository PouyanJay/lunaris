"""P7.5 — the interpret clarifier: merge a learner's confirm answers onto the inferred brief.

These pin the pure merge that lets a learner calibrate their own starting point. The contract: an
absent/empty Clarification is the identity (the zero-friction "accept the inference" default ==
today's inferred-only build), and each confirmed field overrides or augments the matching brief
field — folding self-reported knowledge into ``assumed_prior`` so the existing learner profiler
(which reads it) produces a sharper frontier, with no separate frontier path.
"""

from lunaris_runtime.clarifier import apply_clarification
from lunaris_runtime.schema import (
    Clarification,
    CourseBrief,
    DetailDepth,
    LanguageStyle,
    Level,
    Preferences,
)


def _inferred_brief() -> CourseBrief:
    """A brief as the interpreter would infer it — the starting point the clarifier refines."""
    return CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        target_level=Level.INTERMEDIATE,
        assumed_prior="everyday English",
        audience="an adult learner",
        preferences=Preferences(
            detail_depth=DetailDepth.BALANCED, language_style=LanguageStyle.BALANCED
        ),
    )


def test_no_clarification_returns_the_inferred_brief_unchanged() -> None:
    # Arrange
    brief = _inferred_brief()

    # Act / Assert — None is the identity (the build path when the learner skips the clarifier).
    assert apply_clarification(brief, None) is brief


def test_empty_clarification_is_the_identity_default() -> None:
    # Arrange
    brief = _inferred_brief()

    # Act / Assert — an all-default Clarification ("accept the inference") changes nothing.
    assert apply_clarification(brief, Clarification()) == brief


def test_confirmed_level_overrides_the_inferred_level() -> None:
    # Arrange
    brief = _inferred_brief()  # inferred INTERMEDIATE

    # Act
    merged = apply_clarification(brief, Clarification(target_level=Level.ADVANCED))

    # Assert — the override lands, and the original brief is untouched (pure merge).
    assert merged.target_level == Level.ADVANCED
    assert brief.target_level == Level.INTERMEDIATE


def test_self_reported_knowledge_folds_into_assumed_prior_for_a_sharper_frontier() -> None:
    # Arrange
    brief = _inferred_brief()

    # Act
    merged = apply_clarification(
        brief, Clarification(assumed_known="solid grammar and a wide vocabulary")
    )

    # Assert — the inference is kept AND the self-report is added; the profiler reads assumed_prior,
    # so the report sharpens the frontier (what to skip) without a separate frontier override path.
    assert "everyday English" in merged.assumed_prior
    assert "solid grammar and a wide vocabulary" in merged.assumed_prior


def test_background_folds_into_the_audience() -> None:
    # Arrange
    brief = _inferred_brief()

    # Act
    merged = apply_clarification(brief, Clarification(background="a nurse preparing for licensing"))

    # Assert — appended, not replaced: the inferred audience is kept alongside the self-report.
    assert "an adult learner" in merged.audience
    assert "a nurse preparing for licensing" in merged.audience


def test_both_preference_axes_confirmed_override_the_authoring_voice() -> None:
    # Arrange
    brief = _inferred_brief()

    # Act
    merged = apply_clarification(
        brief,
        Clarification(
            detail_depth=DetailDepth.IN_DEPTH, language_style=LanguageStyle.SOPHISTICATED
        ),
    )

    # Assert
    assert merged.preferences.detail_depth == DetailDepth.IN_DEPTH
    assert merged.preferences.language_style == LanguageStyle.SOPHISTICATED


def test_partial_preference_answer_keeps_the_unspecified_axis_inferred() -> None:
    # Arrange
    brief = _inferred_brief()

    # Act — only the detail axis is confirmed.
    merged = apply_clarification(brief, Clarification(detail_depth=DetailDepth.CONCISE))

    # Assert — the answered axis lands; the unspecified one keeps the inference.
    assert merged.preferences.detail_depth == DetailDepth.CONCISE
    assert merged.preferences.language_style == LanguageStyle.BALANCED
