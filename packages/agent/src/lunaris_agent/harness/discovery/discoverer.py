"""The live grounding discoverer: finds, vets, and ingests evidence for a course's concepts (P6.3).

It ingests a placeholder source for the course's goal concept so the whole path — tool →
discoverer → ``CorpusIngestor`` → per-course corpus, plus the streamed ``SOURCE_EVALUATED`` event —
is exercised with deterministic stubs while the bounded search → fetch → score → reflect loop is
built out behind the same Protocol, report, and wiring.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import structlog
from lunaris_grounding import CandidateSource, CorpusIngestor
from lunaris_runtime.schema import (
    AcquisitionMode,
    AgentEventKind,
    SourceEvaluation,
    SourceType,
    TrustTier,
)

from ..draft import CourseDraft
from .report import DiscoveryReport

logger = structlog.get_logger()

# The KC a discovered source is filed under when the run has no concepts yet (defensive — the agent
# calls discovery after extraction, so concepts are normally present).
_FALLBACK_KC = "grounding"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SubgraphGroundingDiscoverer:
    """Discovers + ingests grounding evidence for a course (the live P6.3 discoverer).

    Holds the corpus ingestor (a Voyage embedder + the pgvector store in production, an in-memory
    store + stub embedder in tests); the ingestor's optional credibility scorer grades each source
    as it lands, so machine-found evidence carries the same graded provenance manual uploads do.
    ``clock`` stamps ``fetched_at`` and is injectable so the offline suite is deterministic.
    """

    def __init__(
        self, ingestor: CorpusIngestor, *, clock: Callable[[], str] = _utc_now_iso
    ) -> None:
        self._ingestor = ingestor
        self._clock = clock

    async def discover(self, draft: CourseDraft) -> DiscoveryReport:
        kc_id = self._target_kc(draft)
        source = self._placeholder_source(kc_id, draft)
        await draft.agent.emit(
            AgentEventKind.SOURCE_EVALUATED,
            source=SourceEvaluation(
                kc_id=kc_id,
                domain="example.org",
                trust_tier=source.trust_tier,
                source_type=source.source_type,
                accepted=True,
                reason="Placeholder grounding source (walking skeleton).",
            ),
        )
        chunks = await self._ingestor.ingest([source], run_id=draft.run_id)
        logger.info(
            "grounding_discovered",
            run_id=draft.run_id,
            course_id=draft.course_id,
            chunks=chunks,
        )
        await draft.agent.emit(
            AgentEventKind.REASONING,
            text=f"Ingested {chunks} grounding chunk(s) for the course corpus.",
        )
        return DiscoveryReport(
            chunks_ingested=chunks,
            sources_accepted=1 if chunks else 0,
            covered_kcs=(kc_id,) if chunks else (),
        )

    @staticmethod
    def _target_kc(draft: CourseDraft) -> str:
        if draft.goal_concept:
            return draft.goal_concept
        if draft.concepts:
            return draft.concepts[0].id
        return _FALLBACK_KC

    def _placeholder_source(self, kc_id: str, draft: CourseDraft) -> CandidateSource:
        subject = draft.brief.subject if draft.brief else draft.topic
        return CandidateSource(
            kc_id=kc_id,
            text=f"Reference material on {subject}.",
            title=f"Grounding for {subject}",
            url="https://example.org/grounding",
            source_type=SourceType.WEB,
            trust_tier=TrustTier.OPEN,
            fetched_at=self._clock(),
            acquisition_mode=AcquisitionMode.AUTO,
            course_id=draft.course_id,
            source_id=f"auto:{draft.course_id}:{kc_id}",
        )
