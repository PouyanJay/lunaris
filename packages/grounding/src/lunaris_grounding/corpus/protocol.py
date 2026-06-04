from typing import Protocol

from lunaris_grounding.corpus.document import GroundingDocument
from lunaris_grounding.corpus.source_summary import CorpusSourceSummary
from lunaris_grounding.evidence import Evidence


class ICorpusStore(Protocol):
    """The vector-store backend for the grounding corpus (D2: Supabase pgvector).

    Retrieval responsibilities are expressed against embeddings so the store stays oblivious to the
    embedding provider: ``upsert`` writes embedded chunks (idempotent on id), and ``match`` returns
    the nearest chunks to a query vector as scored ``Evidence`` (cosine similarity in ``[0, 1]``).
    The management surface (P6.1) folds chunks back into sources for the Corpus UI:
    ``list_sources_for_course`` and ``delete_source``. Substitutable so tests run against an
    in-memory impl.
    """

    async def upsert(self, documents: list[GroundingDocument]) -> int: ...

    async def match(
        self,
        embedding: list[float],
        *,
        k: int = 5,
        min_score: float = 0.0,
        kc_id: str | None = None,
        course_id: str | None = None,
    ) -> list[Evidence]: ...

    async def list_sources_for_course(self, course_id: str) -> list[CorpusSourceSummary]: ...

    async def delete_source(self, source_id: str) -> int: ...
