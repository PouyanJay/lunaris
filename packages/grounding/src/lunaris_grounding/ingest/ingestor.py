import hashlib

import structlog

from lunaris_grounding.corpus.document import GroundingDocument
from lunaris_grounding.corpus.protocol import ICorpusStore
from lunaris_grounding.embeddings.protocol import IEmbedder
from lunaris_grounding.ingest.chunker import chunk_text
from lunaris_grounding.ingest.source import CandidateSource

logger = structlog.get_logger()


class CorpusIngestor:
    """Chunks candidate sources, embeds the chunks, and writes them to the corpus.

    Deterministic assembly (chunking + stable ids) is kept separate from the two injected
    I/O collaborators — the embedder and the store — so it can be tested with a stub
    embedder and an in-memory store. Chunk ids hash kc + content, so re-ingesting the same
    source upserts in place rather than duplicating.
    """

    def __init__(
        self,
        embedder: IEmbedder,
        store: ICorpusStore,
        *,
        max_chars: int = 800,
        overlap: int = 100,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._max_chars = max_chars
        self._overlap = overlap

    async def ingest(self, sources: list[CandidateSource], *, run_id: str | None = None) -> int:
        pending: list[tuple[CandidateSource, str]] = []
        for source in sources:
            for chunk in chunk_text(source.text, max_chars=self._max_chars, overlap=self._overlap):
                pending.append((source, chunk))
        if not pending:
            return 0

        embeddings = await self._embedder.embed([chunk for _, chunk in pending])
        documents = [
            GroundingDocument(
                id=_chunk_id(source.kc_id, chunk),
                kc_id=source.kc_id,
                content=chunk,
                embedding=tuple(embedding),
                title=source.title,
                url=source.url,
                run_id=run_id,
            )
            for (source, chunk), embedding in zip(pending, embeddings, strict=True)
        ]
        written = await self._store.upsert(documents)
        logger.info("corpus_ingested", sources=len(sources), chunks=written)
        return written


def _chunk_id(kc_id: str, content: str) -> str:
    digest = hashlib.sha256(f"{kc_id}|{content}".encode()).hexdigest()
    return f"{kc_id}:{digest[:16]}"
