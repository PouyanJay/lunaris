"""Grounding seed as a tool the agent calls between curriculum and discovery (P6.4).

The agent calls this after ``design_curriculum`` and before ``discover_grounding``, so the
per-course corpus is filled FIRST from the pages the research stage already fetched + vetted, and
discovery only has to cover what the seeds miss. The tool owns the coarse ``GROUNDING_SEEDED`` stage
(so the Grounding phase lights the live build canvas) and delegates the work to the injected
:class:`IGroundingSeeder` — the no-key stub ingests nothing, the live seeder turns the run's
research seeds into graded ``SEED`` corpus sources through the same credibility scorer + trust floor
as every other acquisition mode.
"""

import structlog
from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import ProgressStage

from ..draft import CourseDraft
from ..seeding import IGroundingSeeder, SeedReport

logger = structlog.get_logger()


def make_seed_grounding_tool(seeder: IGroundingSeeder, draft: CourseDraft) -> BaseTool:
    """Build the ``seed_grounding`` tool, closed over the seeder and the run draft."""

    @tool
    async def seed_grounding() -> dict[str, object]:
        """Seed the grounding corpus from the research stage's already-fetched sources. Call after
        design_curriculum and before discover_grounding, so the corpus is filled first from evidence
        the build already read, then discovery covers the gaps. Returns the corpus chunks seeded."""
        # Emit the coarse stage first so any fine-grained seeding events bucket under the Grounding
        # phase in the timeline (the cursor stamps each agent event's stage from it).
        await draft.progress.emit(
            ProgressStage.GROUNDING_SEEDED,
            "Seeding the corpus from already-researched sources",
        )
        # Best-effort (the Protocol's contract): seeding must never abort a build. A failure leaves
        # the corpus as-is and discovery + the verifier handle the now-unsupported claims.
        try:
            report = await seeder.seed(draft)
        except Exception:
            logger.warning("grounding_seed_failed", run_id=draft.run_id, exc_info=True)
            report = SeedReport()
        # Mirror the discover_grounding result shape so the agent reads both grounding tools
        # uniformly (same keys, one per acquisition mode).
        return {
            "status": "ready",
            "sourceCount": report.sources_seeded,
            "chunksIngested": report.chunks_ingested,
        }

    return seed_grounding
