import structlog
from lunaris_runtime.schema import Citation, Claim, RiskTier, TrustTier, VerifierStatus

from lunaris_grounding.discovery.domain_trust import host
from lunaris_grounding.evidence import Evidence
from lunaris_grounding.protocols import IEvidenceRetriever, ISupportAssessor
from lunaris_grounding.thresholds import VerificationThresholds

logger = structlog.get_logger()

# The risk-tiered trust floor (P6.2 §4c), orthogonal to the assessor-score thresholds (now carried
# by ``VerificationThresholds``): those gate how strongly evidence supports a claim, this gates how
# trustworthy the evidence is. Authority order for the floor — VOUCHED (the user chose it) ranks
# with the curated tier; an un-tiered (pre-P6.2) citation is open web, never trusted by omission.
_TIER_RANK: dict[TrustTier, int] = {
    TrustTier.BLOCKED: 0,
    TrustTier.OPEN: 1,
    TrustTier.REPUTABLE: 2,
    TrustTier.VOUCHED: 2,
    TrustTier.OFFICIAL: 3,
}
_UNTIERED_RANK = _TIER_RANK[TrustTier.OPEN]
# A HIGH-risk claim needs curated-or-better evidence (>= REPUTABLE) AND a credibility floor — or
# (per plan §4a) cross-source agreement (>=2 independent domains), so authority can emerge from
# agreement when no single source is curated. LOW risk only excludes blocked sources. The rank
# order is structural (what the tiers MEAN); the tunable values live in VerificationThresholds.
_HIGH_TIER_FLOOR = _TIER_RANK[TrustTier.REPUTABLE]


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

    def __init__(
        self,
        retriever: IEvidenceRetriever,
        assessor: ISupportAssessor,
        *,
        thresholds: VerificationThresholds | None = None,
    ) -> None:
        self._retriever = retriever
        self._assessor = assessor
        # The tunable gates (support thresholds, credibility floor, corroboration minimum) as one
        # injected value object — recalibration is configuration, not a code edit.
        self._thresholds = thresholds or VerificationThresholds()

    @property
    def retriever(self) -> IEvidenceRetriever:
        """The evidence retriever this verifier checks against, read-only (CQ Phase 1.5: grounded
        authoring retrieves from the same corpus the gate will use)."""
        return self._retriever

    async def verify(
        self,
        claims: list[Claim],
        *,
        risk_tier: RiskTier = RiskTier.LOW,
        course_id: str | None = None,
        official_only: bool = False,
    ) -> list[Citation]:
        # ``course_id`` scopes retrieval to the course being built (P6.1): claims ground only
        # against that course's own evidence. The thresholds + the independent assessor are
        # unchanged — this narrows *which* evidence is retrieved, never how strictly it's judged.
        thresholds = self._thresholds
        threshold = (
            thresholds.high_support if risk_tier is RiskTier.HIGH else thresholds.low_support
        )
        citations: dict[str, Citation] = {}

        for claim in claims:
            # Retrieval and assessment are separate live dependencies (vector store +
            # embeddings, then an LLM assessor) that can each be down or rate-limited. We
            # catch them in distinct scopes — same fail-safe outcome (CUT), but distinct
            # log events so an outage in one is never mistaken for the other.
            try:
                evidence = await self._retriever.retrieve(claim.text, course_id=course_id)
            except Exception as exc:
                self._cut_on_grounding_failure(claim, "claim_retrieval_unavailable", exc)
                continue
            try:
                support = await self._assessor.assess(claim.text, evidence)
            except Exception as exc:
                self._cut_on_grounding_failure(claim, "claim_assessment_unavailable", exc)
                continue
            chosen = next((e for e in evidence if e.citation.id == support.citation_id), None)
            agreement = _has_cross_source_agreement(
                evidence, min_domains=thresholds.min_corroborating_domains
            )
            if (
                support.score >= threshold
                and chosen is not None
                and self._within_trust_floor(chosen, agreement, risk_tier, official_only)
            ):
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

    def _within_trust_floor(
        self, chosen: Evidence, agreement: bool, risk_tier: RiskTier, official_only: bool
    ) -> bool:
        """Whether the chosen evidence's authority clears the risk-tiered trust floor (P6.2 §4c).

        Orthogonal to the assessor-score threshold above: that gates how strongly the evidence
        supports the claim; this gates how trustworthy it is. A blocked source is poison everywhere.
        At LOW risk nothing else is excluded (the open web is recorded, not refused). At HIGH the
        evidence must be curated-or-better (>= REPUTABLE, which VOUCHED clears) AND credible — or
        corroborated across >=2 independent domains (``agreement``, over the retrieved set), so a
        single low-trust source can't ground a high-stakes claim (the confirmation-bias trap)
        while real cross-source agreement still can. A cut claim flows through the authoring loop's
        existing triage to ``needs_review``.

        ``official_only`` (P5, the composer's "Official sources only" switch) applies that same
        curated-or-agreement gate at EVERY risk tier, not just HIGH — so an open-web-only claim is
        refused even at LOW risk, while a curated source or genuine cross-source agreement still
        clears it (the safeguard that keeps a tightened build from emptying the course).
        """
        citation = chosen.citation
        rank = _TIER_RANK.get(citation.trust_tier, _UNTIERED_RANK)
        credibility = citation.credibility if citation.credibility is not None else 0.0
        # The curated-or-agreement gate binds on every HIGH-risk claim, and on every claim once the
        # build opts into official-only — collapsed to one flag so the floor rule is one branch.
        strict = risk_tier is RiskTier.HIGH or official_only
        passed = self._floor_ok(rank, credibility, agreement, strict)
        logger.debug(
            "trust_floor_evaluated",
            risk_tier=risk_tier.value,
            official_only=official_only,
            tier=citation.trust_tier.value if citation.trust_tier is not None else None,
            credibility=citation.credibility,
            cross_source_agreement=agreement,
            passed=passed,
        )
        return passed

    def _floor_ok(self, rank: int, credibility: float, agreement: bool, strict: bool) -> bool:
        if rank == _TIER_RANK[TrustTier.BLOCKED]:
            return False  # a blocked/denylisted source never supports a claim, at any risk
        if not strict:
            return True  # the open web is recorded, only blocked is refused
        # Under the strict gate: demand curated-and-credible, or cross-source agreement.
        curated_and_credible = (
            rank >= _HIGH_TIER_FLOOR and credibility >= self._thresholds.high_credibility_floor
        )
        return curated_and_credible or agreement

    def _cut_on_grounding_failure(self, claim: Claim, event: str, exc: Exception) -> None:
        """Fail safe: an unreachable grounding dependency CUTs the claim, never crashes.

        A grounding outage degrades coverage, never correctness — a claim we cannot
        ground is simply not shipped, which still satisfies the publish gate.
        """
        logger.warning(event, error=type(exc).__name__, claim_prefix=claim.text[:120])
        claim.supported_by = None
        claim.verifier_status = VerifierStatus.CUT

    def _assert_publish_gate(self, claims: list[Claim]) -> None:
        """No course ships with a live unsupported claim (build-spec §08)."""
        for claim in claims:
            if claim.supported_by is None and claim.verifier_status is not VerifierStatus.CUT:
                raise AssertionError(
                    f"publish gate violated: unsupported live claim {claim.text!r}"
                )


def _has_cross_source_agreement(evidence: list[Evidence], *, min_domains: int) -> bool:
    """Whether the retrieved evidence is corroborated across >=``min_domains`` independent domains
    (§4b).

    The plan's operationalization of cross-source agreement: count distinct *registrable* domains
    among the retrieved chunks. Grouping by registrable domain (not full host) means two subdomains
    of one site (``blog.mit.edu`` + ``courses.mit.edu``) are one voice, not corroboration — so a
    source can't manufacture agreement from its own subdomains. A BLOCKED (denylisted) domain is
    poison, not a corroborator, so it never counts toward agreement. Evidence with no URL can't be
    attributed to a domain and doesn't count.
    """
    domains = {
        _registrable_domain(e.citation.url)
        for e in evidence
        if e.citation.url and e.citation.trust_tier is not TrustTier.BLOCKED
    }
    domains.discard("")
    return len(domains) >= min_domains


def _registrable_domain(url: str) -> str:
    """A conservative eTLD+1 approximation: the last two labels of the host (``a.b.mit.edu`` →
    ``mit.edu``). Without an eTLD list this over-merges multi-part TLDs (``bbc.co.uk`` → ``co.uk``),
    which only *under-counts* agreement — the moat-safe direction (it cuts more, never less)."""
    labels = host(url).split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else ""
