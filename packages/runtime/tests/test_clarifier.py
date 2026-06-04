"""P7.5 — the interpret clarifier: merge a learner's confirm answers onto the inferred brief.

These pin the pure merge that lets a learner calibrate their own starting point. The contract: an
absent/empty Clarification is the identity (the zero-friction "accept the inference" default ==
today's inferred-only build), and each confirmed field overrides or augments the matching brief
field — folding self-reported knowledge into ``assumed_prior`` so the existing learner profiler
(which reads it) produces a sharper frontier, with no separate frontier path.
"""

import pytest
from lunaris_runtime.clarifier import apply_clarification, build_clarifier
from lunaris_runtime.schema import (
    Clarification,
    Clarifier,
    ClarifierKind,
    ClarifierQuestion,
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


# --- build_clarifier (the "infer" half: derive the confirm questions from the inferred brief) ---


def _question(clarifier: Clarifier, qid: str) -> ClarifierQuestion:
    return next(q for q in clarifier.questions if q.id == qid)


def _recommended(clarifier: Clarifier, qid: str) -> str:
    """The sole recommended option value for a CHOICE question — asserting exactly one is picked."""
    chosen = [o.value for o in _question(clarifier, qid).options if o.recommended]
    assert len(chosen) == 1, f"expected exactly one recommended option for {qid!r}, got {chosen}"
    return chosen[0]


def test_build_clarifier_asks_level_plus_the_four_steering_inputs() -> None:
    # Act
    clarifier = build_clarifier(_inferred_brief())

    # Assert — the §12.1 inputs: level (band) + current knowledge + background + detail + language.
    assert [q.id for q in clarifier.questions] == [
        "level",
        "knowledge",
        "background",
        "detail",
        "language",
    ]


def test_level_question_recommends_the_inferred_level_and_covers_every_band() -> None:
    # Arrange — the interpreter inferred INTERMEDIATE.
    brief = _inferred_brief()

    # Act
    level_q = _question(build_clarifier(brief), "level")

    # Assert — a closed choice over all Level bands; the inferred value pre-picked exactly once.
    assert level_q.kind == ClarifierKind.CHOICE
    assert {o.value for o in level_q.options} == {level.value for level in Level}
    recommended = [o for o in level_q.options if o.recommended]
    assert [o.value for o in recommended] == [Level.INTERMEDIATE.value]


def test_preference_questions_recommend_the_inferred_preferences() -> None:
    # Arrange — inferred BALANCED on both axes.
    clarifier = build_clarifier(_inferred_brief())

    # Assert — each preference question pre-picks the inferred value (zero-friction one-confirm).
    assert _question(clarifier, "detail").kind == ClarifierKind.CHOICE
    assert _recommended(clarifier, "detail") == DetailDepth.BALANCED.value
    assert _recommended(clarifier, "language") == LanguageStyle.BALANCED.value


def test_text_questions_are_free_text_and_seed_knowledge_from_the_inferred_prior() -> None:
    # Arrange — the brief inferred assumed_prior "everyday English".
    clarifier = build_clarifier(_inferred_brief())

    # Assert — knowledge + background are free-TEXT; knowledge is seeded from the inferred prior so
    # the learner can confirm or refine it.
    knowledge_q = _question(clarifier, "knowledge")
    background_q = _question(clarifier, "background")
    assert knowledge_q.kind == ClarifierKind.TEXT
    assert background_q.kind == ClarifierKind.TEXT
    assert "everyday English" in knowledge_q.placeholder
    assert background_q.prompt
    assert "engineer" in background_q.placeholder  # a concrete example hint, not just non-empty


def test_choice_options_carry_human_labels_distinct_from_the_enum_values() -> None:
    # Act
    level_q = _question(build_clarifier(_inferred_brief()), "level")

    # Assert — every option has a non-empty human label (the web renders labels, not enum values).
    assert all(o.label for o in level_q.options)


# --- Variant coverage (P7.5-T4): every enum band, exhaustiveness, the no-prior fallback ---


@pytest.mark.parametrize("level", list(Level))
def test_confirmed_level_overrides_for_every_band(level: Level) -> None:
    # Arrange — the inferred level is INTERMEDIATE; the learner can confirm any band.
    brief = _inferred_brief()

    # Act / Assert — each band lands as the override (including NOT_APPLICABLE).
    assert apply_clarification(brief, Clarification(target_level=level)).target_level == level


@pytest.mark.parametrize("level", list(Level))
def test_build_clarifier_recommends_each_inferred_level(level: Level) -> None:
    # Arrange — a brief inferred at each level in turn.
    brief = _inferred_brief().model_copy(update={"target_level": level})

    # Act / Assert — the level question pre-picks whatever was inferred (incl. NOT_APPLICABLE).
    assert _recommended(build_clarifier(brief), "level") == level.value


@pytest.mark.parametrize("detail", list(DetailDepth))
def test_confirmed_detail_overrides_for_every_band(detail: DetailDepth) -> None:
    # Act / Assert — each band lands on the detail axis it controls.
    merged = apply_clarification(_inferred_brief(), Clarification(detail_depth=detail))
    assert merged.preferences.detail_depth == detail


@pytest.mark.parametrize("language", list(LanguageStyle))
def test_confirmed_language_overrides_for_every_band(language: LanguageStyle) -> None:
    # Act / Assert — each band lands on the language axis it controls.
    merged = apply_clarification(_inferred_brief(), Clarification(language_style=language))
    assert merged.preferences.language_style == language


def test_preference_questions_cover_every_enum_band() -> None:
    # A new enum value with no label would silently get no option — assert exhaustiveness.
    clarifier = build_clarifier(_inferred_brief())
    assert {o.value for o in _question(clarifier, "detail").options} == {
        d.value for d in DetailDepth
    }
    assert {o.value for o in _question(clarifier, "language").options} == {
        s.value for s in LanguageStyle
    }


def test_knowledge_placeholder_falls_back_when_no_prior_was_inferred() -> None:
    # Arrange — a brief with no assumed_prior (the no-key DefaultGoalInterpreter shape).
    brief = CourseBrief(subject="Knitting", goal="knit a scarf")

    # Act
    placeholder = _question(build_clarifier(brief), "knowledge").placeholder

    # Assert — a non-empty fallback hint, not the (absent) inferred prior.
    assert placeholder
    assert "everyday English" not in placeholder
