from dataclasses import dataclass

from lunaris_runtime.schema import TrustTier


@dataclass(frozen=True)
class ScoredSource:
    """The credibility scorer's verdict for a candidate: its resolved trust tier and a credibility.

    Returned by ``ICredibilityScorer.score`` and applied to the candidate before ingestion, so the
    chunk and its citation carry a graded, auditable provenance. ``credibility`` is bounded to
    [0, 1] by the consuming models (``CandidateSource`` / ``GroundingDocument``).
    """

    trust_tier: TrustTier | None
    credibility: float
