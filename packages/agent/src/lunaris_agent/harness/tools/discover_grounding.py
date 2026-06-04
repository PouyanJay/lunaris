"""Grounding discovery as a tool the agent calls between curriculum and authoring (P6.3).

The agent calls this after ``design_curriculum`` and before delegating authoring, so the
per-course evidence corpus is prepared before claims are verified. The tool owns the coarse
``GROUNDING_DISCOVERED`` stage (so the Grounding phase lights the live build canvas) and delegates
the work to the injected :class:`IGroundingDiscoverer` — the no-key stub ingests nothing, the live
discoverer runs the bounded search → fetch → score → ingest loop and streams each source it
evaluates onto the agent channel.
"""

import structlog
from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import ProgressStage

from ..discovery import DiscoveryReport, IGroundingDiscoverer
from ..draft import CourseDraft

logger = structlog.get_logger()


def make_discover_grounding_tool(discoverer: IGroundingDiscoverer, draft: CourseDraft) -> BaseTool:
    """Build the ``discover_grounding`` tool, closed over the discoverer and the run draft."""

    @tool
    async def discover_grounding() -> dict[str, object]:
        """Prepare the grounding corpus for this course's claims. Call after design_curriculum and
        before delegating lesson authoring, so the evidence exists when claims are verified. Finds,
        vets, and ingests sources for the course's concepts; returns the corpus chunks ingested."""
        # Emit the coarse stage first so the discoverer's fine-grained source-vetting events bucket
        # under the Grounding phase in the timeline (the cursor stamps each agent event's stage).
        await draft.progress.emit(
            ProgressStage.GROUNDING_DISCOVERED,
            "Finding and vetting grounding evidence",
        )
        # Best-effort (the Protocol's contract): discovery must never abort a build. A failure
        # leaves the corpus as-is and the verifier cuts the now-unsupported claims into REVIEW.
        try:
            report = await discoverer.discover(draft)
        except Exception:
            logger.warning("grounding_discovery_failed", run_id=draft.run_id, exc_info=True)
            report = DiscoveryReport()
        return {
            "status": "ready",
            "sourceCount": report.sources_accepted,
            "chunksIngested": report.chunks_ingested,
        }

    return discover_grounding
