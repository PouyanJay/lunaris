import hashlib
from dataclasses import replace
from typing import TYPE_CHECKING

import structlog

from lunaris_grounding.corpus.document import GroundingDocument
from lunaris_grounding.corpus.protocol import ICorpusStore
from lunaris_grounding.embeddings.protocol import IEmbedder
from lunaris_grounding.ingest.chunker import chunk_text
from lunaris_grounding.ingest.source import CandidateSource

if TYPE_CHECKING:
    from lunaris_grounding.authorities.scorer_protocol import ICredibilityScorer

logger = structlog.get_logger()


class CorpusIngestor:
    """Chunks candidate sources, embeds the chunks, and writes them to the corpus.

    Deterministic assembly (chunking + stable ids) is kept separate from the two injected
    I/O collaborators — the embedder and the store — so it can be tested with a stub
    embedder and an in-memory store. Chunk ids hash kc + content, so re-ingesting the same
    source upserts in place rather than duplicating.

    An optional ``scorer`` (P6.2) grades a source's trust tier + credibility just before ingestion,
    so the chunk and its citation carry a graded, auditable provenance. A source acquired already
    classified (a VOUCHED manual upload) keeps its tier; the scorer only fills what is unset.
    """

    def __init__(
        self,
        embedder: IEmbedder,
        store: ICorpusStore,
        *,
        scorer: "ICredibilityScorer | None" = None,
        max_chars: int = 800,
        overlap: int = 100,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._scorer = scorer
        self._max_chars = max_chars
        self._overlap = overlap

    async def ingest(self, sources: list[CandidateSource], *, run_id: str | None = None) -> int:
        sources = [await self._scored(source) for source in sources]
        pending: list[tuple[CandidateSource, str]] = []
        for source in sources:
            for chunk in chunk_text(source.text, max_chars=self._max_chars, overlap=self._overlap):
                pending.append((source, chunk))
        if not pending:
            return 0

        embeddings = await self._embedder.embed([chunk for _, chunk in pending])
        documents = [
            _to_document(source, chunk, embedding, run_id)
            for (source, chunk), embedding in zip(pending, embeddings, strict=True)
        ]
        written = await self._store.upsert(documents)
        logger.info("corpus_ingested", sources=len(sources), chunks=written)
        return written

    async def _scored(self, source: CandidateSource) -> CandidateSource:
        """Grade an unscored source's trust tier + credibility (P6.2), leaving set fields untouched.

        No scorer (the legacy path), or a source already carrying both a tier and a credibility,
        passes through unchanged — so this is backward-compatible and the manual-ingest VOUCHED tier
        survives. Otherwise the scorer fills each *independently*: a tier only when none was given,
        a credibility only when it was missing (so a half-classified source can't end up un-tiered).
        """
        if self._scorer is None or (
            source.trust_tier is not None and source.credibility is not None
        ):
            return source
        scored = await self._scorer.score(source)
        return replace(
            source,
            trust_tier=source.trust_tier or scored.trust_tier,
            credibility=source.credibility
            if source.credibility is not None
            else scored.credibility,
        )


def _to_document(
    source: CandidateSource, chunk: str, embedding: list[float], run_id: str | None
) -> GroundingDocument:
    """Build one corpus chunk, carrying the source's trust/provenance set (P6.0) untouched."""
    return GroundingDocument(
        id=_chunk_id(source.kc_id, chunk),
        kc_id=source.kc_id,
        content=chunk,
        embedding=tuple(embedding),
        title=source.title,
        url=source.url,
        run_id=run_id,
        source_type=source.source_type,
        trust_tier=source.trust_tier,
        credibility=source.credibility,
        fetched_at=source.fetched_at,
        acquisition_mode=source.acquisition_mode,
        course_id=source.course_id,
        source_id=source.source_id,
    )


def _chunk_id(kc_id: str, content: str) -> str:
    digest = hashlib.sha256(f"{kc_id}|{content}".encode()).hexdigest()
    return f"{kc_id}:{digest[:16]}"
