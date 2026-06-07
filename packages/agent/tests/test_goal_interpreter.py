"""P7.0 — the goal interpreter: the parser, the schema contract, the stub, and the tool.

Covers the new front of the pipeline in isolation: ``parse_brief`` turning the model's JSON into a
validated ``CourseBrief`` (tolerant of prose/fences + malformed fields, defaulting rather than
crashing), the ``CourseBrief`` camelCase wire contract, the stub, and the ``interpret_request`` tool
recording the brief on the draft and emitting ``BRIEF_INTERPRETED``. The full end-to-end flow
through the harness is covered by ``test_agent_course_build``.
"""

import pytest
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.progress_reporter import ProgressReporter
from lunaris_agent.harness.tools import make_interpret_request_tool
from lunaris_agent.subagents.goal_interpreter import (
    DefaultGoalInterpreter,
    StubGoalInterpreter,
    parse_brief,
)
from lunaris_runtime.schema import (
    CourseBrief,
    DeliverableShape,
    DetailDepth,
    Gap,
    GapMagnitude,
    GoalType,
    LanguageStyle,
    Level,
    Preferences,
    ProgressStage,
    StandardKind,
    TargetStandard,
)
from pydantic import ValidationError

_FULL_BRIEF_JSON = """Here is the brief:
{
  "subject": "English language proficiency",
  "goal": "reach CLB 10 across all four skills",
  "goal_type": "credential",
  "gap": {"entry_level": "advanced", "magnitude": "moderate"},
  "target_standard": {"name": "CLB 10", "kind": "external_standard",
                      "authority_hint": "ircc.canada.ca"},
  "target_level": "advanced",
  "assumed_prior": "strong everyday English (CLB 8-9)",
  "audience": "an adult learner already fluent",
  "deliverable_shape": {"lessons": 6},
  "needs_research": true,
  "domain_field": "language-learning",
  "preferences": {"detail_depth": "in_depth", "language_style": "sophisticated"}
}
That's the interpretation."""


def test_parse_brief_reads_every_field_from_prose_wrapped_json() -> None:
    # Arrange — _FULL_BRIEF_JSON (module-level): a complete brief wrapped in prose.
    # Act — the model wraps the JSON in prose (a common live slip); the parser extracts it.
    brief = parse_brief(_FULL_BRIEF_JSON)

    # Assert — every field maps, enums coerce, and the named standard carries its authority hint.
    assert brief.subject == "English language proficiency"
    assert brief.goal == "reach CLB 10 across all four skills"
    assert brief.goal_type is GoalType.CREDENTIAL
    # The gap reads the inferred entry level + magnitude; its target_level is synced from the brief.
    assert brief.gap.entry_level is Level.ADVANCED
    assert brief.gap.target_level is Level.ADVANCED
    assert brief.gap.magnitude is GapMagnitude.MODERATE
    assert brief.target_level is Level.ADVANCED
    assert brief.target_standard is not None
    assert brief.target_standard.name == "CLB 10"
    assert brief.target_standard.kind is StandardKind.EXTERNAL_STANDARD
    assert brief.target_standard.authority_hint == "ircc.canada.ca"
    assert brief.assumed_prior == "strong everyday English (CLB 8-9)"
    assert brief.audience == "an adult learner already fluent"
    assert brief.deliverable_shape.lessons == 6
    assert brief.needs_research is True
    assert brief.domain_field == "language-learning"
    assert brief.preferences.detail_depth is DetailDepth.IN_DEPTH
    assert brief.preferences.language_style is LanguageStyle.SOPHISTICATED


def test_parse_brief_defaults_missing_optionals_and_bad_enums() -> None:
    # Arrange — a minimal brief with out-of-vocabulary enum values everywhere.
    text = (
        '{"subject": "Knitting", "goal": "knit a scarf", "target_level": "wizard",'
        ' "goal_type": "telepathy", "gap": {"entry_level": "wizard", "magnitude": "epic"},'
        ' "preferences": {"detail_depth": "epic", "language_style": "alien"}}'
    )

    # Act
    brief = parse_brief(text)

    # Assert — unknown enum values fall back to safe defaults; absent optionals take their defaults.
    assert brief.target_level is Level.NOT_APPLICABLE
    assert brief.goal_type is GoalType.KNOWLEDGE
    assert brief.gap.entry_level is Level.NOT_APPLICABLE
    assert brief.gap.target_level is Level.NOT_APPLICABLE  # synced to the brief's target_level
    assert brief.gap.magnitude is GapMagnitude.MODERATE
    assert brief.target_standard is None
    assert brief.deliverable_shape.lessons is None
    assert brief.needs_research is False
    assert brief.domain_field == ""
    assert brief.preferences.detail_depth is DetailDepth.BALANCED
    assert brief.preferences.language_style is LanguageStyle.BALANCED


def test_parse_brief_syncs_gap_target_level_to_the_brief_target_level() -> None:
    # Arrange — the model gives a gap whose target_level disagrees with the brief's target_level
    # (a common live slip). The brief's target_level is authoritative; the gap must not drift.
    text = (
        '{"subject": "s", "goal": "g", "target_level": "expert",'
        ' "gap": {"entry_level": "intermediate", "target_level": "novice", "magnitude": "large"}}'
    )

    # Act
    brief = parse_brief(text)

    # Assert — gap.target_level is forced to match the brief; entry_level + magnitude are preserved.
    assert brief.target_level is Level.EXPERT
    assert brief.gap.target_level is Level.EXPERT
    assert brief.gap.entry_level is Level.INTERMEDIATE
    assert brief.gap.magnitude is GapMagnitude.LARGE


def test_parse_brief_drops_a_standard_without_a_name() -> None:
    # Arrange — a target_standard object that names nothing is not a usable standard.
    text = '{"subject": "s", "goal": "g", "target_standard": {"kind": "exam"}}'

    # Act / Assert — no name → no standard (rather than a blank one).
    assert parse_brief(text).target_standard is None


@pytest.mark.parametrize("lessons", ['"six"', "0", "-3", "null"])
def test_parse_brief_drops_a_non_positive_or_non_numeric_lesson_count(lessons: str) -> None:
    # Arrange — a deliverable shape whose lesson count is unusable.
    text = f'{{"subject": "s", "goal": "g", "deliverable_shape": {{"lessons": {lessons}}}}}'

    # Act / Assert — an unusable count collapses to None (no constraint), never crashes.
    assert parse_brief(text).deliverable_shape.lessons is None


def test_parse_brief_backfills_subject_from_goal() -> None:
    # Arrange — the model gave a goal but no subject.
    text = '{"goal": "master distributed consensus"}'

    # Act
    brief = parse_brief(text)

    # Assert — both fields are populated so every later stage has a subject and a goal.
    assert brief.subject == "master distributed consensus"
    assert brief.goal == "master distributed consensus"


def test_parse_brief_backfills_goal_from_subject() -> None:
    # Arrange — the reverse: a subject but no goal (the backfill must work both directions).
    text = '{"subject": "distributed consensus"}'

    # Act
    brief = parse_brief(text)

    # Assert
    assert brief.subject == "distributed consensus"
    assert brief.goal == "distributed consensus"


def test_parse_brief_raises_when_there_is_no_json() -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        parse_brief("I could not interpret that request.")


def test_parse_brief_raises_when_neither_subject_nor_goal_present() -> None:
    with pytest.raises(ValueError, match="neither a subject nor a goal"):
        parse_brief('{"audience": "someone", "needs_research": true}')


def test_course_brief_round_trips_through_the_camelcase_wire() -> None:
    # Arrange
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        goal_type=GoalType.CREDENTIAL,
        gap=Gap(entry_level=Level.ADVANCED, magnitude=GapMagnitude.MODERATE),
        target_standard=TargetStandard(name="CLB 10", authority_hint="ircc.canada.ca"),
        target_level=Level.ADVANCED,
        deliverable_shape=DeliverableShape(lessons=6),
        needs_research=True,
        preferences=Preferences(
            detail_depth=DetailDepth.IN_DEPTH, language_style=LanguageStyle.SOPHISTICATED
        ),
    )

    # Act — the wire form the web consumes is camelCase with enum values as strings.
    wire = brief.model_dump(mode="json", by_alias=True)

    # Assert — camelCase keys, string enums, and a lossless round-trip back to the model.
    assert wire["targetLevel"] == "advanced"
    assert wire["goalType"] == "credential"
    assert wire["gap"]["entryLevel"] == "advanced"
    assert wire["gap"]["magnitude"] == "moderate"
    assert wire["targetStandard"]["authorityHint"] == "ircc.canada.ca"
    assert wire["deliverableShape"]["lessons"] == 6
    assert wire["preferences"]["detailDepth"] == "in_depth"
    assert CourseBrief.model_validate(wire) == brief


def test_course_brief_rejects_unknown_fields() -> None:
    # Unknown keys are a contract violation (extra="forbid"), not silently dropped.
    with pytest.raises(ValidationError):
        CourseBrief.model_validate({"subject": "s", "goal": "g", "bogus": 1})


def test_nested_brief_models_also_reject_unknown_fields() -> None:
    # extra="forbid" is inherited from CourseModel, so the nested contracts enforce it too.
    with pytest.raises(ValidationError):
        TargetStandard.model_validate({"name": "CLB 10", "rogue_field": 1})


async def test_stub_goal_interpreter_returns_its_configured_brief() -> None:
    brief = CourseBrief(subject="s", goal="g")
    interpreter = StubGoalInterpreter(brief)

    assert await interpreter.interpret("any request") is brief


async def test_interpret_request_tool_records_the_brief_and_emits_the_stage(progress_sink) -> None:
    # Arrange — the tool over a draft with a recording progress reporter wired in.
    draft = CourseDraft(topic="demo", course_id="c", run_id="r")
    draft.progress = ProgressReporter("r", progress_sink)
    brief = CourseBrief(subject="English", goal="reach CLB 10", target_level=Level.ADVANCED)
    tool = make_interpret_request_tool(StubGoalInterpreter(brief), draft)

    # Act
    result = await tool.ainvoke({"request": "Improve my English to CLB 10"})

    # Assert — the typed brief is recorded on the draft for later stages, the tool returns the
    # camelCase brief for the agent/timeline, and exactly one BRIEF_INTERPRETED stage is emitted.
    assert draft.brief == brief
    assert result["subject"] == "English"
    assert result["targetLevel"] == "advanced"
    assert [event.stage for event in progress_sink.events] == [ProgressStage.BRIEF_INTERPRETED]
    assert progress_sink.events[0].run_id == "r"


# --- DefaultGoalInterpreter (P7.5): the key-free, topic-derived fallback for the brief endpoint ---


async def test_default_goal_interpreter_derives_a_topic_brief_without_a_model() -> None:
    # Arrange — no model/key; the deterministic fallback the brief endpoint uses without a key.
    interpreter = DefaultGoalInterpreter()

    # Act
    brief = await interpreter.interpret("  Improve my English to CLB 10  ")

    # Assert — a sensible default brief from the (trimmed) topic, with no inferred level/prefs, so
    # the clarifier offers the learner the chance to fill them in.
    assert brief.subject == "Improve my English to CLB 10"
    assert brief.goal == "Improve my English to CLB 10"
    assert brief.target_level == Level.NOT_APPLICABLE
    assert brief.preferences == Preferences()
