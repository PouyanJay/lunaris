import pytest
from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    InMemoryCorpusStore,
    StubEmbedder,
)
from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier

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


async def test_ingest_carries_trust_provenance_through_to_retrieval() -> None:
    # Arrange — a stub source acquired WITH a trust classification + per-course scoping (P6.0).
    store = InMemoryCorpusStore()
    ingestor = CorpusIngestor(StubEmbedder(dim=_DIM), store)
    text = "A short, single-chunk grounding source."
    source = CandidateSource(
        kc_id="kc1",
        text=text,
        title="Notes",
        url="https://example.edu/notes",
        source_type=SourceType.REFERENCE,
        trust_tier=TrustTier.REPUTABLE,
        credibility=0.88,
        fetched_at="2026-06-03T00:00:00Z",
        acquisition_mode=AcquisitionMode.MANUAL,
        course_id="course-1",
    )

    # Act — ingest, then retrieve within the source's course.
    written = await ingestor.ingest([source], run_id="run-1")
    [query] = await StubEmbedder(dim=_DIM).embed([text])
    [evidence] = await store.match(query, k=written, course_id="course-1")

    # Assert — the trust/provenance set at acquisition reaches the citation untouched (end-to-end
    # roundtrip: CandidateSource → CorpusIngestor → GroundingDocument → match → Citation).
    assert written == 1
    assert evidence.citation.trust_tier is TrustTier.REPUTABLE
    assert evidence.citation.credibility == 0.88
    assert evidence.citation.source_type is SourceType.REFERENCE
    assert evidence.citation.fetched_at == "2026-06-03T00:00:00Z"

    # The ingestor copied course_id onto the chunk: a different course retrieves nothing. Guards the
    # silent failure where trust passes on an unfiltered match but scoping is quietly broken.
    assert await store.match(query, k=written, course_id="course-2") == []


async def test_ingest_unclassified_source_carries_no_trust() -> None:
    # Arrange — a source with no trust classification (the legacy / not-yet-scored path).
    store = InMemoryCorpusStore()
    ingestor = CorpusIngestor(StubEmbedder(dim=_DIM), store)
    text = "An un-tiered grounding source."

    # Act — ingest, then retrieve (no trust fields supplied).
    await ingestor.ingest([CandidateSource(kc_id="kc1", text=text)])
    [query] = await StubEmbedder(dim=_DIM).embed([text])
    [evidence] = await store.match(query, k=1)

    # Assert — the chunk stores + retrieves, with no trust fields (so the reader shows no badge).
    assert evidence.citation.trust_tier is None
    assert evidence.citation.credibility is None
    assert evidence.citation.source_type is None
    assert evidence.citation.fetched_at is None


def test_candidate_source_rejects_out_of_range_credibility() -> None:
    # The credibility bound is validated where the source is acquired, not deferred downstream.
    with pytest.raises(ValueError, match=r"credibility must be in \[0, 1\]"):
        CandidateSource(kc_id="kc1", text="t", credibility=-0.1)


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
