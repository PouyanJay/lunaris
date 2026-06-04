from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from lunaris_grounding.authorities.scored_source import ScoredSource
    from lunaris_grounding.ingest.source import CandidateSource


class ICredibilityScorer(Protocol):
    """Scores a candidate source's trust tier + credibility before ingestion (P6.2, §4b).

    Injected into the ``CorpusIngestor`` so the embedding/store path stays oblivious to *how* a
    source is graded; the deterministic blend is swappable and tests run with a stub. Returns the
    resolved tier and a credibility in [0, 1] that flow onto the chunk and the citation.
    """

    async def score(self, source: "CandidateSource") -> "ScoredSource": ...
