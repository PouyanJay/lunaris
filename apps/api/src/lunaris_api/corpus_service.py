"""The manual-ingest service (P6.1): user-supplied sources → the source-quality gate → the corpus.

The product surface for "manual mode" (plan §3): a learner adds their own trusted documents to a
course's grounding corpus, and curates them. This service composes the embedder + corpus store into
a ``CorpusIngestor`` and owns the gate that stamps a source's provenance (VOUCHED tier, MANUAL mode,
a ``source_id`` so it can be listed + deleted as one source) before ingestion. Real document
extraction (PDF/DOCX/URL) and dedup land in later tasks; T0 ingests pasted text.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    CorpusSourceSummary,
    ICorpusStore,
    IEmbedder,
)
from lunaris_runtime.schema import AcquisitionMode, TrustTier

# Manual sources are general course evidence, not tied to one KC; the verifier searches the whole
# course corpus (kc_id=None), so this sentinel KC just satisfies the chunk key.
_MANUAL_KC = "manual"


@dataclass(frozen=True)
class IngestOutcome:
    """The gate's verdict for a submitted source: accepted (with id + chunk count), or declined."""

    accepted: bool
    source_id: str
    chunks: int
    reason: str | None = None


class CorpusService:
    """Ingests, lists, and deletes a course's manually-provided grounding sources."""

    def __init__(self, store: ICorpusStore, embedder: IEmbedder) -> None:
        self._store = store
        self._ingestor = CorpusIngestor(embedder, store)

    async def add_text(self, *, course_id: str, title: str | None, text: str) -> IngestOutcome:
        """Ingest a pasted/plain-text source into the course's corpus as a VOUCHED manual source."""
        source_id = uuid4().hex
        if not text.strip():
            return IngestOutcome(
                accepted=False, source_id=source_id, chunks=0, reason="empty source"
            )
        source = CandidateSource(
            kc_id=_MANUAL_KC,
            text=text,
            title=title,
            trust_tier=TrustTier.VOUCHED,
            acquisition_mode=AcquisitionMode.MANUAL,
            fetched_at=datetime.now(UTC).isoformat(),
            course_id=course_id,
            source_id=source_id,
        )
        chunks = await self._ingestor.ingest([source])
        return IngestOutcome(accepted=True, source_id=source_id, chunks=chunks)

    async def list_sources(self, course_id: str) -> list[CorpusSourceSummary]:
        """The course's manually-ingested sources, folded from their chunks (for the Corpus UI)."""
        return await self._store.list_sources_for_course(course_id)

    async def delete_source(self, source_id: str) -> int:
        """Remove a source (all its chunks) from the corpus; returns the chunk count removed."""
        return await self._store.delete_source(source_id)
