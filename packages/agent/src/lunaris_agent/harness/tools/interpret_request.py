"""Intent interpretation as the agent's first tool (thin adapter over ``IGoalInterpreter``).

The very front of the build: turn the raw request into a typed ``CourseBrief`` — a goal for a
learner at a level — and record it on the run draft so every later stage designs backward from the
right desired result instead of enumerating a subject bottom-up. The LLM-heavy interpretation stays
in the goal-interpreter subagent (live Claude or a stub); this wraps it, records the typed brief,
emits the ``BRIEF_INTERPRETED`` stage, and returns the brief for the agent to confirm and the live
timeline to render.
"""

from langchain_core.tools import BaseTool, tool
from lunaris_runtime.clarifier import apply_clarification
from lunaris_runtime.schema import ProgressStage

from ...subagents.goal_interpreter import IGoalInterpreter
from ..draft import CourseDraft


def make_interpret_request_tool(interpreter: IGoalInterpreter, draft: CourseDraft) -> BaseTool:
    """Build the ``interpret_request`` tool, closed over the interpreter and the run draft.

    The tool records the typed brief on ``draft.brief`` (authoritative, read by later stages) and
    returns the brief as a compact camelCase dict the agent reasons over and the timeline renders.
    """

    @tool
    async def interpret_request(request: str) -> dict[str, object]:
        """Interpret the request into a brief — call this FIRST, before extracting concepts.

        Reads the request as a GOAL for a learner at a level: subject, goal, target level, any named
        standard, assumed prior knowledge, and explicit constraints (e.g. a lesson count). The brief
        is recorded for the later stages automatically; you do NOT need to pass it back. Returns the
        brief so you can confirm the interpretation before extracting concepts.
        """
        brief = await interpreter.interpret(request)
        # Fold in the learner's opt-in confirm answers (P7.5), if any. None / a skipped clarifier is
        # the identity, so the default build records the interpreter's inference verbatim.
        brief = apply_clarification(brief, draft.clarification)
        draft.brief = brief
        await draft.progress.emit(
            ProgressStage.BRIEF_INTERPRETED,
            f"Interpreted the goal: {brief.goal}",
        )
        return brief.model_dump(mode="json", by_alias=True)

    return interpret_request
