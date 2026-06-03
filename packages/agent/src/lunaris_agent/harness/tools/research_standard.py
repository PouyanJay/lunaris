"""Research the standard as a tool the agent calls (thin adapter over ``IStandardResearcher``).

After the request is interpreted, ground the brief's target standard in its *real* competency
descriptors before designing: the LLM-heavy research (search → fetch → extract → distil) stays in
the researcher subagent (live or a stub); this wraps it, records the findings on the brief
(``draft.brief.research``, read by extraction + the curriculum architect), emits
``STANDARD_RESEARCHED``, and returns the findings for the agent to confirm and the live source-
vetting table to render. Always-on but bounded + best-effort: it degrades honestly to
``UNAVAILABLE`` when no source is reachable, and skips cleanly if the brief is missing.
"""

from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import ProgressStage, ResearchStatus, StandardResearch

from ...subagents.standard_researcher import IStandardResearcher
from ..draft import CourseDraft


def make_research_standard_tool(researcher: IStandardResearcher, draft: CourseDraft) -> BaseTool:
    """Build the ``research_standard`` tool, closed over the researcher and the run draft.

    Records the grounded research on ``draft.brief.research`` via a copy (the brief is
    frozen-at-generation in spirit) and returns it compactly for the agent + the live timeline.
    Degrades to ``UNAVAILABLE`` if the brief is missing — the build stays robust even if
    interpretation was skipped.
    """

    @tool
    async def research_standard() -> dict[str, object]:
        """Research the brief's target standard — after interpret_request, before model_learner.

        Grounds the goal in the standard's real competency descriptors (and any score/threshold
        lines) by searching + reading authoritative sources, so the later stages design backward
        from the actual standard, not memory. The findings are recorded on the brief automatically;
        you do NOT need to pass them back. Returns the findings (competencies + vetted sources with
        provenance) so you can confirm the grounding before modeling the learner.
        """
        if draft.brief is None:
            research = StandardResearch(status=ResearchStatus.UNAVAILABLE)
        else:
            research = await researcher.research(draft.brief)
            draft.brief = draft.brief.model_copy(update={"research": research})
        await draft.progress.emit(
            ProgressStage.STANDARD_RESEARCHED,
            f"Researched the standard: {research.status.value}, "
            f"{len(research.competencies)} competency descriptor(s)",
        )
        return research.model_dump(mode="json", by_alias=True)

    return research_standard
