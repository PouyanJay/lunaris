"""P7.1 — the learner profiler: the parser, the stub, and the model_learner tool.

Covers the model-the-learner stage in isolation: ``parse_profile`` turning the model's JSON into a
``LearnerProfile`` (tolerant of prose/fences; an absent/malformed frontier degrades to empty =
novice), the stub, and the ``model_learner`` tool recording ``draft.frontier`` and emitting
``LEARNER_MODELED``. The full end-to-end flow through the harness is covered by
``test_agent_course_build``.
"""

from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.progress_reporter import ProgressReporter
from lunaris_agent.harness.tools import make_model_learner_tool
from lunaris_agent.subagents.learner_profiler import (
    LearnerProfile,
    StubLearnerProfiler,
    parse_profile,
)
from lunaris_runtime.schema import CourseBrief, Level, ProgressStage


def test_parse_profile_reads_the_frontier_from_prose_wrapped_json() -> None:
    text = """Here's what they already know:
    {"frontier": ["the English alphabet", "everyday vocabulary", "basic grammar"]}
    That's the frontier."""

    profile = parse_profile(text)

    assert profile.frontier == ["the English alphabet", "everyday vocabulary", "basic grammar"]


def test_parse_profile_filters_blank_entries() -> None:
    profile = parse_profile('{"frontier": ["arrays", "  ", "", "loops"]}')

    assert profile.frontier == ["arrays", "loops"]


def test_parse_profile_degrades_to_empty_when_frontier_absent() -> None:
    # A novice (no frontier key) → empty list → the course teaches from the foundations.
    assert parse_profile('{"note": "nothing known"}').frontier == []


def test_parse_profile_degrades_to_empty_on_no_json() -> None:
    # Unparseable model output must not crash the build; it degrades to novice.
    assert parse_profile("I could not determine the frontier.").frontier == []


def test_parse_profile_degrades_to_empty_when_frontier_is_not_a_list() -> None:
    assert parse_profile('{"frontier": "everything"}').frontier == []


async def test_stub_learner_profiler_returns_its_configured_profile() -> None:
    profile = LearnerProfile(frontier=["arrays"])
    profiler = StubLearnerProfiler(profile)
    brief = CourseBrief(subject="s", goal="g")

    assert await profiler.profile(brief) is profile


async def test_model_learner_tool_records_the_frontier_and_emits_the_stage(progress_sink) -> None:
    # Arrange — a brief on the draft + a profiler that returns a known frontier.
    draft = CourseDraft(topic="demo", course_id="c", run_id="r")
    draft.brief = CourseBrief(subject="English", goal="reach CLB 10", target_level=Level.ADVANCED)
    draft.progress = ProgressReporter("r", progress_sink)
    profiler = StubLearnerProfiler(LearnerProfile(frontier=["the alphabet", "basic vocabulary"]))
    tool = make_model_learner_tool(profiler, draft)

    # Act
    result = await tool.ainvoke({})

    # Assert — the frontier is recorded for extraction + the graph, returned compactly, and exactly
    # one LEARNER_MODELED stage is emitted.
    assert draft.frontier == ["the alphabet", "basic vocabulary"]
    assert result["frontier"] == ["the alphabet", "basic vocabulary"]
    assert result["count"] == 2
    assert [event.stage for event in progress_sink.events] == [ProgressStage.LEARNER_MODELED]
    assert progress_sink.events[0].run_id == "r"


async def test_model_learner_tool_assumes_a_novice_when_the_brief_is_missing(progress_sink) -> None:
    # Arrange — no brief on the draft (interpret was skipped) → assume a novice, teach foundations.
    draft = CourseDraft(topic="demo", course_id="c", run_id="r")
    draft.progress = ProgressReporter("r", progress_sink)
    profiler = StubLearnerProfiler(LearnerProfile(frontier=["should-not-be-used"]))
    tool = make_model_learner_tool(profiler, draft)

    # Act
    result = await tool.ainvoke({})

    # Assert — empty frontier (novice), profiler not consulted, stage still emitted + correlated.
    assert draft.frontier == []
    assert result["count"] == 0
    assert [event.stage for event in progress_sink.events] == [ProgressStage.LEARNER_MODELED]
    assert progress_sink.events[0].run_id == "r"
