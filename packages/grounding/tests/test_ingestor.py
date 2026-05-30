from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    InMemoryCorpusStore,
    StubEmbedder,
)

# Shared by the ingestor fixtures and the query embedder below — they MUST match, or
# InMemoryCorpusStore raises on a dimension mismatch instead of failing the assertion cleanly.
_DIM = 128
_LONG_TEXT = " ".join(f"concept{i} explained clearly" for i in range(60))


async def test_ingest_chunks_embeds_and_writes_to_the_store() -> None:
    # Arrange — one long source that must split into several chunks
    store = InMemoryCorpusStore()
    ingestor = CorpusIngestor(StubEmbedder(dim=_DIM), store, max_chars=80, overlap=10)
    source = CandidateSource(kc_id="kc1", text=_LONG_TEXT, title="T", url="u")

    # Act
    written = await ingestor.ingest([source], run_id="run-1")

    # Assert — multiple chunks written and retrievable under the KC
    assert written > 1
    matches = await store.match(await _embed_query(), k=written + 5, kc_id="kc1")
    assert len(matches) == written


async def test_reingesting_the_same_source_is_idempotent() -> None:
    # Arrange
    store = InMemoryCorpusStore()
    ingestor = CorpusIngestor(StubEmbedder(dim=_DIM), store, max_chars=80, overlap=10)
    source = CandidateSource(kc_id="kc1", text=_LONG_TEXT)

    # Act — ingest the identical source twice (deterministic chunk ids)
    first = await ingestor.ingest([source])
    await ingestor.ingest([source])
    matches = await store.match(await _embed_query(), k=first + 50, kc_id="kc1")

    # Assert — second pass upserts in place, no duplicates
    assert len(matches) == first


async def test_empty_source_writes_nothing() -> None:
    # Arrange
    store = InMemoryCorpusStore()
    ingestor = CorpusIngestor(StubEmbedder(), store)

    # Act
    written = await ingestor.ingest([CandidateSource(kc_id="kc1", text="   ")])

    # Assert
    assert written == 0


async def _embed_query() -> list[float]:
    [vector] = await StubEmbedder(dim=_DIM).embed(["concept0 explained clearly"])
    return vector
