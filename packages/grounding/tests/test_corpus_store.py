from lunaris_grounding import GroundingDocument, InMemoryCorpusStore


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


async def test_upsert_is_idempotent_on_id() -> None:
    # Arrange
    store = InMemoryCorpusStore()
    await store.upsert([_doc("dup", "kc1", (1.0, 0.0))])

    # Act — same id again
    await store.upsert([_doc("dup", "kc1", (1.0, 0.0))])
    results = await store.match([1.0, 0.0], k=10)

    # Assert — not duplicated
    assert len(results) == 1
