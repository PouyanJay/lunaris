import structlog
from lunaris_runtime.schema import Citation, Claim, RiskTier, VerifierStatus

from lunaris_grounding.protocols import IEvidenceRetriever, ISupportAssessor

logger = structlog.get_logger()

_HIGH_THRESHOLD = 0.85
_LOW_THRESHOLD = 0.65


class Verifier:
    """The deterministic Failure-B moat (build-spec §08).

    Operates per-claim, not per-paragraph, so a single bad sentence can't ride along
    inside otherwise-correct text. For each claim it retrieves evidence, asks an
    independent assessor whether the evidence supports it, and marks the claim
    SUPPORTED (with its citation) or CUT. Enforces the publish gate: no claim is left
    live and unsupported.

    MVP policy is binary (supported/cut); the build-spec's "revise → back to author"
    loop is a V1 refinement. The retriever + assessor are injected (DIP) so the corpus
    backend and the model are swappable and tests run with stubs.
    """

    def __init__(self, retriever: IEvidenceRetriever, assessor: ISupportAssessor) -> None:
        self._retriever = retriever
        self._assessor = assessor

    async def verify(
        self, claims: list[Claim], *, risk_tier: RiskTier = RiskTier.LOW
    ) -> list[Citation]:
        threshold = _HIGH_THRESHOLD if risk_tier is RiskTier.HIGH else _LOW_THRESHOLD
        citations: dict[str, Citation] = {}

        for claim in claims:
            evidence = await self._retriever.retrieve(claim.text)
            support = await self._assessor.assess(claim.text, evidence)
            chosen = next((e for e in evidence if e.citation.id == support.citation_id), None)
            if support.score >= threshold and chosen is not None:
                claim.supported_by = chosen.citation.id
                claim.verifier_status = VerifierStatus.SUPPORTED
                citations[chosen.citation.id] = chosen.citation
            else:
                claim.supported_by = None
                claim.verifier_status = VerifierStatus.CUT

        self._assert_publish_gate(claims)
        supported = sum(1 for c in claims if c.verifier_status is VerifierStatus.SUPPORTED)
        logger.info(
            "claims_verified",
            total=len(claims),
            supported=supported,
            cut=len(claims) - supported,
        )
        return list(citations.values())

    def _assert_publish_gate(self, claims: list[Claim]) -> None:
        """No course ships with a live unsupported claim (build-spec §08)."""
        for claim in claims:
            if claim.supported_by is None and claim.verifier_status is not VerifierStatus.CUT:
                raise AssertionError(
                    f"publish gate violated: unsupported live claim {claim.text!r}"
                )
