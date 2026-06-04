import pytest
from lunaris_grounding import GroundingDocument, InMemoryCorpusStore
from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier


def _doc(doc_id: str, kc_id: str, embedding: tuple[float, ...]) -> GroundingDocument:
    return GroundingDocument(
        id=doc_id, kc_id=kc_id, content=f"content for {doc_id}", embedding=embedding
    )


async def test_match_returns_nearest_document_first() -> None:
    # Arrange — three orthogonal-ish unit vectors; query points at the second
    store = InMemoryCorpusStore()
    await store.upsert(
        [
            _doc("a", "kc1", (1.0, 0.0, 0.0)),
            _doc("b", "kc1", (0.0, 1.0, 0.0)),
            _doc("c", "kc1", (0.0, 0.0, 1.0)),
        ]
    )

    # Act
    results = await store.match([0.1, 0.9, 0.0], k=3)

    # Assert — closest (b) ranks first, scores descending
    assert results[0].citation.id == "b"
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


async def test_match_respects_k_limit() -> None:
    # Arrange
    store = InMemoryCorpusStore()
    await store.upsert([_doc(str(i), "kc1", (float(i), 1.0)) for i in range(5)])

    # Act
    results = await store.match([1.0, 1.0], k=2)

    # Assert
    assert len(results) == 2


async def test_match_filters_below_min_score() -> None:
    # Arrange — one aligned (cosine 1.0), one opposite (cosine -1.0)
    store = InMemoryCorpusStore()
    await store.upsert([_doc("aligned", "kc1", (1.0, 0.0)), _doc("opposite", "kc1", (-1.0, 0.0))])

    # Act
    results = await store.match([1.0, 0.0], k=5, min_score=0.5)

    # Assert — only the aligned doc clears the floor
    assert [r.citation.id for r in results] == ["aligned"]


async def test_match_filters_by_kc_id() -> None:
    # Arrange — same vector under two different KCs
    store = InMemoryCorpusStore()
    await store.upsert([_doc("x", "kc1", (1.0, 0.0)), _doc("y", "kc2", (1.0, 0.0))])

    # Act
    results = await store.match([1.0, 0.0], kc_id="kc2")

    # Assert
    assert [r.citation.id for r in results] == ["y"]


async def test_match_carries_trust_and_provenance_onto_the_citation() -> None:
    # Arrange — a document ingested with the full P6.0 trust/provenance set.
    store = InMemoryCorpusStore()
    await store.upsert(
        [
            GroundingDocument(
                id="d1",
                kc_id="kc1",
                content="Dijkstra relaxes edges to find shortest paths.",
                embedding=(1.0, 0.0),
                title="Algorithms",
                url="https://en.wikipedia.org/wiki/Dijkstra",
                trust_tier=TrustTier.REPUTABLE,
                credibility=0.91,
                source_type=SourceType.REFERENCE,
                fetched_at="2026-06-03T00:00:00Z",
                acquisition_mode=AcquisitionMode.SEED,
                course_id="course-1",
            )
        ]
    )

    # Act — retrieve through the course-scoped path real grounding uses (not the legacy whole-corpus
    # mode), so this proves the scoping guard and the citation enrichment don't conflict.
    [evidence] = await store.match([1.0, 0.0], k=1, course_id="course-1")

    # Assert — trust/provenance constructed at acquisition flows untouched onto the citation
    # (provenance-is-structural). course_id/acquisition_mode stay corpus-internal (not on the wire).
    citation = evidence.citation
    assert citation.trust_tier is TrustTier.REPUTABLE
    assert citation.credibility == 0.91
    assert citation.source_type is SourceType.REFERENCE
    assert citation.fetched_at == "2026-06-03T00:00:00Z"


async def test_match_is_scoped_to_the_active_course() -> None:
    # Arrange — the same vector under two different courses, plus a legacy null-course doc.
    store = InMemoryCorpusStore()
    await store.upsert(
        [
            _doc("legacy", "kc1", (1.0, 0.0)),  # course_id=None (pre-P6.0 / keyless ingest)
            GroundingDocument(
                id="c1", kc_id="kc1", content="c1", embedding=(1.0, 0.0), course_id="course-1"
            ),
            GroundingDocument(
                id="c2", kc_id="kc1", content="c2", embedding=(1.0, 0.0), course_id="course-2"
            ),
        ]
    )

    # Act — retrieval for course-1 must see ONLY course-1's chunk: never course-2's, never the
    # null-course one. Owner decision: per-course scoping is structural — no cross-topic bleed.
    results = await store.match([1.0, 0.0], k=10, course_id="course-1")

    # Assert
    assert [r.citation.id for r in results] == ["c1"]


async def test_match_without_a_course_filter_searches_all() -> None:
    # Arrange — two course-keyed chunks plus a legacy null-course chunk (pre-P6.0 / keyless ingest).
    store = InMemoryCorpusStore()
    await store.upsert(
        [
            _doc("legacy", "kc1", (1.0, 0.0)),  # course_id=None
            GroundingDocument(
                id="c1", kc_id="kc1", content="c1", embedding=(1.0, 0.0), course_id="course-1"
            ),
            GroundingDocument(
                id="c2", kc_id="kc1", content="c2", embedding=(1.0, 0.0), course_id="course-2"
            ),
        ]
    )

    # Act — the legacy/no-course path (course_id=None) keeps today's whole-corpus behaviour, so the
    # not-yet-wired live verifier and the MCP surface are unaffected.
    results = await store.match([1.0, 0.0], k=10)

    # Assert — every chunk comes back when no filter is supplied, including the null-course one.
    assert {r.citation.id for r in results} == {"legacy", "c1", "c2"}


def test_grounding_document_rejects_out_of_range_credibility() -> None:
    # A bad credibility must fail at the entity boundary (where it's acquired), not silently flow to
    # the citation's [0, 1] wire check deep inside match().
    with pytest.raises(ValueError, match=r"credibility must be in \[0, 1\]"):
        GroundingDocument(id="d", kc_id="kc1", content="c", embedding=(1.0,), credibility=1.5)


async def test_list_sources_folds_chunks_by_source_and_skips_unkeyed() -> None:
    # Arrange — two chunks of source s1, one chunk of s2, and a legacy unkeyed chunk.
    store = InMemoryCorpusStore()
    await store.upsert(
        [
            GroundingDocument(
                id="a",
                kc_id="kc1",
                content="a",
                embedding=(1.0, 0.0),
                title="Notes",
                trust_tier=TrustTier.VOUCHED,
                course_id="c1",
                source_id="s1",
            ),
            GroundingDocument(
                id="b",
                kc_id="kc1",
                content="b",
                embedding=(1.0, 0.0),
                title="Notes",
                trust_tier=TrustTier.VOUCHED,
                course_id="c1",
                source_id="s1",
            ),
            GroundingDocument(
                id="c",
                kc_id="kc1",
                content="c",
                embedding=(1.0, 0.0),
                course_id="c1",
                source_id="s2",
            ),
            _doc("legacy", "kc1", (1.0, 0.0)),  # course_id=None, source_id=None — excluded
        ]
    )

    # Act
    sources = await store.list_sources_for_course("c1")

    # Assert — two sources; s1 folds its two chunks into one row carrying its provenance.
    by_id = {s.source_id: s for s in sources}
    assert set(by_id) == {"s1", "s2"}
    assert by_id["s1"].chunk_count == 2
    assert by_id["s1"].title == "Notes"
    assert by_id["s1"].trust_tier is TrustTier.VOUCHED


async def test_delete_source_removes_its_chunks_and_is_idempotent() -> None:
    # Arrange
    store = InMemoryCorpusStore()
    await store.upsert(
        [
            GroundingDocument(
                id="a",
                kc_id="kc1",
                content="a",
                embedding=(1.0, 0.0),
                course_id="c1",
                source_id="s1",
            ),
            GroundingDocument(
                id="b",
                kc_id="kc1",
                content="b",
                embedding=(1.0, 0.0),
                course_id="c1",
                source_id="s1",
            ),
        ]
    )

    # Act / Assert — first delete removes both chunks; a repeat delete removes nothing (idempotent).
    assert await store.delete_source("s1") == 2
    assert await store.list_sources_for_course("c1") == []
    assert await store.delete_source("s1") == 0


async def test_upsert_is_idempotent_on_id() -> None:
    # Arrange
    store = InMemoryCorpusStore()
    await store.upsert([_doc("dup", "kc1", (1.0, 0.0))])

    # Act — same id again
    await store.upsert([_doc("dup", "kc1", (1.0, 0.0))])
    results = await store.match([1.0, 0.0], k=10)

    # Assert — not duplicated
    assert len(results) == 1
