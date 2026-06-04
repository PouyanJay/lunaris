"""The manual-ingest service (P6.1): user-supplied sources → the source-quality gate → the corpus.

The product surface for "manual mode" (plan §3): a learner adds their own trusted documents to a
course's grounding corpus, and curates them. This service composes the embedder + corpus store into
a ``CorpusIngestor`` and owns the gate that stamps a source's provenance (VOUCHED tier, MANUAL mode,
a deterministic ``source_id`` so it can be listed + deleted as one source, and so re-adding the same
content/URL is a no-op duplicate) before ingestion. Three input shapes share one gate + ingest path:
pasted text, an uploaded file (PDF/DOCX/MD/TXT via ``IDocumentExtractor``), and a URL (fetched +
extracted via the shared ``IContentExtractor``). The credibility scorer + the risk-tiered trust
floor are P6.2; this gate only dedups + stamps vouched provenance.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    CorpusSourceSummary,
    DocumentExtractor,
    IContentExtractor,
    ICorpusStore,
    IDocumentExtractor,
    IEmbedder,
    TrafilaturaContentExtractor,
    classify_domain,
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
    """Ingests (text / file / URL), lists, and deletes a course's manual grounding sources."""

    def __init__(
        self,
        store: ICorpusStore,
        embedder: IEmbedder,
        *,
        content_extractor: IContentExtractor | None = None,
        document_extractor: IDocumentExtractor | None = None,
    ) -> None:
        self._store = store
        self._ingestor = CorpusIngestor(embedder, store)
        self._content_extractor = content_extractor or TrafilaturaContentExtractor()
        self._document_extractor = document_extractor or DocumentExtractor()

    async def add_text(self, *, course_id: str, title: str | None, text: str) -> IngestOutcome:
        """Ingest a pasted/plain-text source into the course's corpus."""
        return await self._ingest(course_id, text=text, title=title, url=None)

    async def add_file(
        self, *, course_id: str, filename: str, content_type: str | None, data: bytes
    ) -> IngestOutcome:
        """Extract text from an uploaded file (PDF/DOCX/MD/TXT) and ingest it."""
        extracted = await self._document_extractor.extract(
            filename=filename, content_type=content_type, data=data
        )
        if extracted is None:
            return IngestOutcome(
                accepted=False, source_id="", chunks=0, reason="unsupported or empty file"
            )
        return await self._ingest(
            course_id, text=extracted.text, title=extracted.title or filename, url=None
        )

    async def add_url(self, *, course_id: str, url: str) -> IngestOutcome:
        """Fetch a URL, extract its main text, and ingest it (keyed to the URL for dedup).

        SSRF guard: the shared ``classify_domain`` blocks denylisted domains + internal/loopback/
        link-local IPs (e.g. cloud-metadata endpoints) before the server ever fetches the URL.
        """
        if classify_domain(url) is TrustTier.BLOCKED:
            return IngestOutcome(
                accepted=False, source_id="", chunks=0, reason="that URL is not allowed"
            )
        extracted = await self._content_extractor.extract(url)
        if extracted is None:
            return IngestOutcome(
                accepted=False, source_id="", chunks=0, reason="could not fetch or extract the URL"
            )
        return await self._ingest(
            course_id, text=extracted.text, title=extracted.title or url, url=url
        )

    async def list_sources(self, course_id: str) -> list[CorpusSourceSummary]:
        """The course's manually-ingested sources, folded from their chunks (for the Corpus UI)."""
        return await self._store.list_sources_for_course(course_id)

    async def delete_source(self, source_id: str) -> int:
        """Remove a source (all its chunks) from the corpus; returns the chunk count removed."""
        return await self._store.delete_source(source_id)

    async def _ingest(
        self, course_id: str, *, text: str, title: str | None, url: str | None
    ) -> IngestOutcome:
        """The shared gate: dedup on the deterministic source id, then stamp + ingest."""
        source_id = _source_id(course_id, url=url, text=text)
        if not text.strip():
            return IngestOutcome(
                accepted=False, source_id=source_id, chunks=0, reason="empty source"
            )
        # Dedup by listing the course's sources (O(n) — fine at manual-curation scale; a dedicated
        # store existence check is a future optimisation if the corpus grows large).
        existing = await self._store.list_sources_for_course(course_id)
        if any(summary.source_id == source_id for summary in existing):
            return IngestOutcome(
                accepted=False, source_id=source_id, chunks=0, reason="already in the corpus"
            )
        source = CandidateSource(
            kc_id=_MANUAL_KC,
            text=text,
            title=title,
            url=url,
            trust_tier=TrustTier.VOUCHED,
            acquisition_mode=AcquisitionMode.MANUAL,
            fetched_at=datetime.now(UTC).isoformat(),
            course_id=course_id,
            source_id=source_id,
        )
        chunks = await self._ingestor.ingest([source])
        return IngestOutcome(accepted=True, source_id=source_id, chunks=chunks)


def _source_id(course_id: str, *, url: str | None, text: str) -> str:
    """A deterministic per-source id: same course + same URL (or content) → same id, so the gate
    rejects a re-add as a duplicate and ingestion stays idempotent. URL-keyed when present (so the
    same page is one source regardless of extracted text), else content-keyed."""
    key = url if url else text
    return hashlib.sha256(f"{course_id}|{key}".encode()).hexdigest()[:32]
