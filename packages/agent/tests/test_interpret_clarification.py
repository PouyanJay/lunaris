"""P7.5 — the interpret_request tool merges the opt-in clarification onto the inferred brief.

The tool layer of the seam: the goal interpreter infers a brief; if the run carries a learner's
confirm answers (``draft.clarification``), the tool folds them in before recording ``draft.brief``,
so every later stage (profiler → extractor → architect → author) designs from the calibrated brief.
With no clarification it records the inference verbatim (today's path).
"""

from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_interpret_request_tool
from lunaris_agent.subagents.goal_interpreter import StubGoalInterpreter
from lunaris_runtime.schema import Clarification, CourseBrief, Level

_INFERRED = CourseBrief(
    subject="English language proficiency",
    goal="reach CLB 10",
    target_level=Level.INTERMEDIATE,
    assumed_prior="everyday English",
)


async def test_interpret_request_records_the_inferred_brief_when_no_clarification() -> None:
    # Arrange — the default path: the run carries no clarification.
    draft = CourseDraft(topic="demo", course_id="c", run_id="r")
    tool = make_interpret_request_tool(StubGoalInterpreter(_INFERRED), draft)

    # Act
    result = await tool.ainvoke({"request": "demo"})

    # Assert — the interpreter's inference is recorded verbatim (camelCase on the wire).
    assert draft.brief is not None
    assert draft.brief.target_level == Level.INTERMEDIATE
    assert result["targetLevel"] == "intermediate"


async def test_interpret_request_merges_the_clarification_onto_the_brief() -> None:
    # Arrange — an opt-in clarification confirms a higher level + reports prior knowledge.
    draft = CourseDraft(topic="demo", course_id="c", run_id="r")
    draft.clarification = Clarification(
        target_level=Level.ADVANCED, assumed_known="solid grammar and a wide vocabulary"
    )
    tool = make_interpret_request_tool(StubGoalInterpreter(_INFERRED), draft)

    # Act
    result = await tool.ainvoke({"request": "demo"})

    # Assert — the recorded brief is the calibrated one: the level is overridden and the self-report
    # is folded into assumed_prior (which the profiler reads → a sharper frontier). The returned
    # dict surfaces the merged brief for the agent + the live timeline.
    assert draft.brief is not None
    assert draft.brief.target_level == Level.ADVANCED
    assert "solid grammar and a wide vocabulary" in draft.brief.assumed_prior
    assert result["targetLevel"] == "advanced"
