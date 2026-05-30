"""Live grounded eval (Stage 4b): ingest real sources into Supabase pgvector, embed with
the hosted model, and prove a claim is grounded against the corpus end-to-end.

Gated on the D2 creds — ``SUPABASE_URL``, ``SUPABASE_SERVICE_ROLE_KEY`` and
``EMBEDDINGS_API_KEY``. Until those are set this skips (the deterministic suite already
proves the pathway against the in-memory store). Excluded from the default run (``eval``):

    uv run --env-file .env pytest -m eval -q
"""

import os

import pytest
from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    PgVectorRetriever,
    StubSupportAssessor,
    SupabaseCorpusStore,
    Verifier,
    VoyageEmbedder,
)
from lunaris_runtime.schema import Claim, VerifierStatus

pytestmark = pytest.mark.eval

_HAS_CREDS = bool(
    os.getenv("SUPABASE_URL")
    and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    and os.getenv("EMBEDDINGS_API_KEY")
)

_SOURCE = CandidateSource(
    kc_id="binary_search",
    title="Binary Search",
    url="https://example.org/binary-search",
    text=(
        "Binary search repeatedly halves a sorted array, comparing the target to the middle "
        "element and discarding the half that cannot contain it. Because the search space "
        "halves on each step, binary search runs in logarithmic time."
    ),
)


@pytest.mark.skipif(not _HAS_CREDS, reason="Supabase/embeddings creds not set")
async def test_real_corpus_grounds_a_claim() -> None:
    # Arrange — embed + ingest into the live pgvector corpus, then wire the real retriever
    embedder = VoyageEmbedder()
    store = SupabaseCorpusStore()
    await CorpusIngestor(embedder, store).ingest([_SOURCE], run_id="eval-4b")
    # Floor for real voyage-3.5 cosines (a different distribution than the feature-hash stub's
    # ~0.45 gap); recalibrate when switching embedding models.
    retriever = PgVectorRetriever(embedder, store, min_score=0.3)
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="Binary search runs in logarithmic time by halving the search space")

    # Act
    citations = await verifier.verify([claim])

    # Assert — grounded against real embeddings + a real vector store
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    assert len(citations) == 1
