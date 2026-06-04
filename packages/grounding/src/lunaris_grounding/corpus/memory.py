import math

from lunaris_runtime.schema import Citation

from lunaris_grounding.corpus.document import GroundingDocument
from lunaris_grounding.evidence import Evidence


class InMemoryCorpusStore:
    """An in-process cosine-similarity corpus — the deterministic test backbone.

    Implements the same contract as the Supabase pgvector store using real cosine
    similarity over stored vectors, so the retrieve → assess → verify pathway (and a claim
    actually reaching SUPPORTED) can be proven offline without a database or a vector
    extension. Not for production: it holds the whole corpus in memory and scans linearly.
    """

    def __init__(self) -> None:
        self._documents: dict[str, GroundingDocument] = {}

    async def upsert(self, documents: list[GroundingDocument]) -> int:
        for document in documents:
            self._documents[document.id] = document
        return len(documents)

    async def match(
        self,
        embedding: list[float],
        *,
        k: int = 5,
        min_score: float = 0.0,
        kc_id: str | None = None,
        course_id: str | None = None,
    ) -> list[Evidence]:
        scored: list[Evidence] = []
        for document in self._documents.values():
            if kc_id is not None and document.kc_id != kc_id:
                continue
            # Per-course scoping (P6.0): when a course is requested, only its own chunks match —
            # never another course's, never a null-course (legacy) chunk. Retrieval over a
            # "close but not identical" topic must not surface that topic's evidence (no bleed).
            if course_id is not None and document.course_id != course_id:
                continue
            score = _cosine(embedding, document.embedding)
            if score < min_score:
                continue
            citation = Citation(
                id=document.id,
                title=document.title,
                url=document.url,
                snippet=document.content,
                trust_tier=document.trust_tier,
                credibility=document.credibility,
                source_type=document.source_type,
                fetched_at=document.fetched_at,
            )
            scored.append(Evidence(citation=citation, score=score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:k]


def _cosine(left: list[float], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions differ")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
