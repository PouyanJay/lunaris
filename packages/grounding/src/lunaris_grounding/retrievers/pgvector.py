from lunaris_grounding.corpus.protocol import ICorpusStore
from lunaris_grounding.embeddings.protocol import IEmbedder
from lunaris_grounding.evidence import Evidence

_DEFAULT_K = 5
_DEFAULT_MIN_SCORE = 0.25


class PgVectorRetriever:
    """The real ``IEvidenceRetriever`` (D2): embed the claim, then nearest-neighbour the corpus.

    Composes an embedder with a corpus store (Supabase pgvector in production, an in-memory
    cosine store in tests) — both injected, so neither the embedding provider nor the vector
    backend is hardwired. ``min_score`` floors retrieval relevance; the assessor then makes
    the independent supported/cut call downstream. Searches the whole course corpus by
    default (``kc_id=None``) since the verifier sees only the claim text.
    """

    def __init__(
        self,
        embedder: IEmbedder,
        store: ICorpusStore,
        *,
        k: int = _DEFAULT_K,
        min_score: float = _DEFAULT_MIN_SCORE,
        kc_id: str | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._k = k
        self._min_score = min_score
        self._kc_id = kc_id

    async def retrieve(self, claim_text: str) -> list[Evidence]:
        embeddings = await self._embedder.embed([claim_text])
        if not embeddings:
            return []
        return await self._store.match(
            embeddings[0], k=self._k, min_score=self._min_score, kc_id=self._kc_id
        )
