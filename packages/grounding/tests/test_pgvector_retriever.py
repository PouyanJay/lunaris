"""The Stage 4b payoff: a real retriever lets a claim reach SUPPORTED.

With the old stub retriever every claim was CUT (no corpus). These tests use the
deterministic stub embedder + in-memory cosine store to prove the retrieve → assess →
verify pathway grounds a claim against an ingested source — and still cuts the ungrounded.
"""

from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    InMemoryCorpusStore,
    PgVectorRetriever,
    StubEmbedder,
    StubSupportAssessor,
    Verifier,
)
from lunaris_runtime.schema import Claim, VerifierStatus

_SOURCE = CandidateSource(
    kc_id="binary_search",
    title="Binary Search",
    url="https://example.org/binary-search",
    text=(
        "Binary search repeatedly halves a sorted array, comparing the target to the "
        "middle element and discarding the half that cannot contain it. Because the "
        "search space halves each step, it runs in logarithmic time."
    ),
)


# Floor sits in the clean gap between a grounded claim (~0.52 cosine under the feature-hash
# stub) and an unrelated one (~0.32). The tests below ASSERT both sides of this gap so that a
# future StubEmbedder change fails loudly here instead of silently miscalibrating the suite.
_MIN_SCORE = 0.45


async def _grounded_retriever() -> PgVectorRetriever:
    embedder = StubEmbedder(dim=512)
    store = InMemoryCorpusStore()
    await CorpusIngestor(embedder, store).ingest([_SOURCE], run_id="run-1")
    return PgVectorRetriever(embedder, store, min_score=_MIN_SCORE)


async def test_retrieve_returns_evidence_for_a_grounded_claim() -> None:
    # Arrange
    retriever = await _grounded_retriever()

    # Act
    evidence = await retriever.retrieve("binary search halves the sorted array each step")

    # Assert — evidence comes back, carrying a citation with the source url, and clears the floor
    assert evidence
    assert evidence[0].citation.url == _SOURCE.url
    assert evidence[0].score > _MIN_SCORE, (
        f"grounded score {evidence[0].score:.3f} did not clear min_score={_MIN_SCORE}; "
        "the StubEmbedder gap may have shifted — recalibrate _MIN_SCORE."
    )


async def test_grounded_claim_reaches_supported_through_the_verifier() -> None:
    # Arrange — the full Failure-B pathway with a real corpus behind it
    retriever = await _grounded_retriever()
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="Binary search runs in logarithmic time by halving the search space")

    # Act
    citations = await verifier.verify([claim])

    # Assert — previously impossible with the stub retriever: the claim is SUPPORTED + cited
    assert claim.verifier_status is VerifierStatus.SUPPORTED
    assert claim.supported_by is not None
    assert len(citations) == 1


async def test_ungrounded_claim_is_still_cut() -> None:
    # Arrange — corpus is about binary search; claim is unrelated
    retriever = await _grounded_retriever()
    verifier = Verifier(retriever, StubSupportAssessor())
    claim = Claim(text="Mitochondria are the powerhouse of the cell")

    # Act
    await verifier.verify([claim])

    # Assert — no spurious grounding; the publish gate cuts it
    assert claim.verifier_status is VerifierStatus.CUT
    # And the separation is the floor's doing: the unrelated claim retrieves nothing above it.
    assert await retriever.retrieve(claim.text) == [], (
        f"unrelated claim cleared min_score={_MIN_SCORE}; the StubEmbedder gap has narrowed."
    )
