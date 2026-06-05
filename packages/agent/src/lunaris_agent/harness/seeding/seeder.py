"""The live grounding seeder: ingests the research stage's already-fetched pages into the corpus.

The near-free half of the hybrid corpus (P6.4). The research stage (P7.2) already searched, fetched,
extracted, and trust-classified authoritative pages to ground the brief; this turns that same
material into ``SEED`` corpus sources so the build's claims can be verified against the evidence it
read to design the course — no second fetch. Every seed is graded by the SAME credibility scorer
(carried by the ingestor) and gated at verify by the SAME risk-tiered trust floor as a manual upload
or an auto-discovered page: seeded is not the same as trusted.
"""

import hashlib
from typing import TYPE_CHECKING

import structlog
from lunaris_grounding import CandidateSource, CorpusIngestor
from lunaris_runtime.schema import AcquisitionMode, SourceType

from ..draft import CourseDraft
from .report import SeedReport

if TYPE_CHECKING:
    from ...subagents.standard_researcher import SeedSource

logger = structlog.get_logger()

# Research seeds ground the standard broadly, not one KC — and the verifier searches the whole
# course corpus by claim text (kc_id is unused at verify), so this sentinel just keys the chunk.
# Mirrors the manual ingestor's ``manual`` sentinel.
_SEED_KC = "seed"


class GroundingSeeder:
    """Seeds a course's corpus from ``draft.research_seeds`` by ingesting the already-fetched text.

    Holds the corpus ingestor (a Voyage embedder + the pgvector store in production, an in-memory
    store + stub embedder in tests). The ingestor carries the credibility scorer, which fills each
    seed's credibility at ingestion — the seed arrives tier-classified (from research) but unscored,
    so it earns its credibility through the same gate as every other source. Best-effort: an empty
    seed list (the no-key / unavailable-research path) ingests nothing and reports an empty pass.
    """

    def __init__(self, ingestor: CorpusIngestor) -> None:
        self._ingestor = ingestor

    async def seed(self, draft: CourseDraft) -> SeedReport:
        seeds = draft.research_seeds
        if not seeds:
            return SeedReport()
        sources = [_to_source(seed, draft.course_id) for seed in seeds]
        chunks = await self._ingestor.ingest(sources, run_id=draft.run_id)
        logger.info(
            "grounding_seeded",
            run_id=draft.run_id,
            course_id=draft.course_id,
            sources=len(sources),
            chunks=chunks,
        )
        return SeedReport(sources_seeded=len(sources), chunks_ingested=chunks)


def _to_source(seed: "SeedSource", course_id: str) -> CandidateSource:
    """Turn a research-stage fetched page into a ``SEED`` corpus source, scoped to the course.

    Carries the seed's acquisition-time trust tier + ``fetched_at`` (structural provenance) and
    leaves credibility unset, so the ingestor's scorer grades it. ``source_id`` is a deterministic
    fingerprint of (course, url) so re-seeding the same page upserts in place, not duplicating it.
    """
    return CandidateSource(
        kc_id=_SEED_KC,
        text=seed.text,
        title=seed.title,
        url=seed.url,
        source_type=SourceType.WEB,
        trust_tier=seed.trust_tier,
        fetched_at=seed.fetched_at,
        acquisition_mode=AcquisitionMode.SEED,
        course_id=course_id,
        source_id=_source_id(course_id, seed.url),
    )


def _source_id(course_id: str, url: str) -> str:
    """A deterministic per-source id (course + url) so re-seeding a page is idempotent."""
    return hashlib.sha256(f"{course_id}|{url}".encode()).hexdigest()[:32]
