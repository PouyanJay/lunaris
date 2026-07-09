import math

from lunaris_runtime.schema import Citation

from lunaris_grounding.corpus.document import GroundingDocument
from lunaris_grounding.corpus.source_summary import CorpusSourceSummary
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

    async def list_sources_for_course(self, course_id: str) -> list[CorpusSourceSummary]:
        # Fold the course's chunks into sources by source_id. Legacy/agent-path chunks (no
        # source_id) are excluded — only manually-ingested sources are managed at source level.
        by_source: dict[str, list[GroundingDocument]] = {}
        for document in self._documents.values():
            if document.course_id != course_id or document.source_id is None:
                continue
            by_source.setdefault(document.source_id, []).append(document)
        return [_summarize(source_id, chunks) for source_id, chunks in by_source.items()]

    async def delete_source(self, source_id: str) -> int:
        removed = [doc_id for doc_id, doc in self._documents.items() if doc.source_id == source_id]
        for doc_id in removed:
            del self._documents[doc_id]
        return len(removed)

    async def delete_for_course(self, course_id: str) -> int:
        removed = [doc_id for doc_id, doc in self._documents.items() if doc.course_id == course_id]
        for doc_id in removed:
            del self._documents[doc_id]
        return len(removed)


def _summarize(source_id: str, chunks: list[GroundingDocument]) -> CorpusSourceSummary:
    """Fold a source's chunks into one summary (provenance from any chunk; they share it)."""
    head = chunks[0]
    return CorpusSourceSummary(
        source_id=source_id,
        course_id=head.course_id,
        title=head.title,
        url=head.url,
        source_type=head.source_type,
        trust_tier=head.trust_tier,
        credibility=head.credibility,
        acquisition_mode=head.acquisition_mode,
        fetched_at=head.fetched_at,
        chunk_count=len(chunks),
    )


def _cosine(left: list[float], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions differ")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
