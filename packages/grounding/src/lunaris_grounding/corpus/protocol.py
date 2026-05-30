from typing import Protocol

from lunaris_grounding.corpus.document import GroundingDocument
from lunaris_grounding.evidence import Evidence


class ICorpusStore(Protocol):
    """The vector-store backend for the grounding corpus (D2: Supabase pgvector).

    Two responsibilities, both expressed against embeddings so the store stays oblivious
    to the embedding provider: ``upsert`` writes embedded chunks (idempotent on id), and
    ``match`` returns the nearest chunks to a query vector as scored ``Evidence`` (cosine
    similarity in ``[0, 1]``). Substitutable so tests run against an in-memory cosine impl.
    """

    async def upsert(self, documents: list[GroundingDocument]) -> int: ...

    async def match(
        self,
        embedding: list[float],
        *,
        k: int = 5,
        min_score: float = 0.0,
        kc_id: str | None = None,
    ) -> list[Evidence]: ...
