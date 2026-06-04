"""Grounding discovery as a tool the agent calls between curriculum and authoring (P6.0 scaffold).

P6.0 stands up the *seam* where the discovery sub-graph will run (P6.3): the agent calls this after
``design_curriculum`` and before delegating authoring, so the evidence corpus is prepared before
claims are verified. For now it is a stub — it records the ``GROUNDING_DISCOVERED`` stage so the
live build canvas shows the Grounding phase end-to-end; the real search → fetch → score → ingest
loop (and the live source-vetting table) land in P6.3. Per-course retrieval is wired (P6.0-T0/T1).
"""

from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import AgentEventKind, ProgressStage

from ..draft import CourseDraft


def make_discover_grounding_tool(draft: CourseDraft) -> BaseTool:
    """Build the stub ``discover_grounding`` tool, closed over the run draft."""

    @tool
    async def discover_grounding() -> dict[str, object]:
        """Prepare the grounding corpus for this course's claims. Call after design_curriculum and
        before delegating lesson authoring, so the evidence exists when claims are verified. (P6.0:
        a scaffold that readies the per-course corpus; automatic source discovery lands later.)"""
        await draft.progress.emit(
            ProgressStage.GROUNDING_DISCOVERED,
            "Prepared the grounding corpus",
        )
        await draft.agent.emit(
            AgentEventKind.REASONING,
            text="Readying the grounding corpus for this course before authoring.",
        )
        return {"status": "ready", "sourceCount": 0}

    return discover_grounding
