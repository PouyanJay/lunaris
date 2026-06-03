"""Model the learner as the second stage (thin adapter over ``ILearnerProfiler``).

After the request is interpreted into a brief, infer what a learner at that level already knows —
the frontier the course must NOT re-teach — and record it on the run draft so the next stage
(extraction) scopes to the gap instead of enumerating the whole ladder from zero. The LLM-heavy
inference stays in the profiler subagent; this wraps it, records ``draft.frontier``, emits
``LEARNER_MODELED``.
"""

from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import ProgressStage

from ...subagents.learner_profiler import ILearnerProfiler
from ..draft import CourseDraft


def make_model_learner_tool(profiler: ILearnerProfiler, draft: CourseDraft) -> BaseTool:
    """Build the ``model_learner`` tool, closed over the profiler and the run draft.

    Records the inferred frontier on ``draft.frontier`` (read by extraction + the graph) and returns
    it compactly for the agent + the live timeline. Degrades to a novice (empty frontier) if the
    brief is missing — the build stays robust even if interpretation was skipped.
    """

    @tool
    async def model_learner() -> dict[str, object]:
        """Model the learner — call this after research_standard, before extraction.

        Infers the learner's frontier (the foundations a learner at the brief's level already knows,
        which the course must NOT teach) from the brief (which research_standard has grounded), and
        records it for gap-scoped extraction. The frontier is recorded automatically; you do NOT
        need to pass it back. Returns the frontier so you can confirm what will be skipped.
        """
        if draft.brief is None:
            draft.frontier = []
        else:
            profile = await profiler.profile(draft.brief)
            draft.frontier = list(profile.frontier)
        await draft.progress.emit(
            ProgressStage.LEARNER_MODELED,
            f"Modeled the learner: {len(draft.frontier)} known area(s)",
        )
        return {"frontier": list(draft.frontier), "count": len(draft.frontier)}

    return model_learner
