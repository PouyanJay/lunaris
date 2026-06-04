from collections.abc import Mapping

import structlog
from lunaris_runtime.schema import AuthorityKind, TrustTier

from lunaris_grounding.authorities.authority import SourceAuthority
from lunaris_grounding.authorities.scored_source import ScoredSource
from lunaris_grounding.authorities.store_protocol import ISourceAuthorityStore
from lunaris_grounding.discovery.domain_trust import classify_domain, host
from lunaris_grounding.ingest.source import CandidateSource

logger = structlog.get_logger()

# The tier prior → a base credibility, the dominant signal in the §4b blend (T2 layers recency,
# extraction quality and KC-relevance on top). Deliberately ordered: a user-vouched source sits just
# below an official body but above the general web, and a blocked domain scores zero. A source with
# no tier defaults to the open-web prior, never to "trusted by omission".
_DEFAULT_PRIORS: Mapping[TrustTier, float] = {
    TrustTier.OFFICIAL: 0.90,
    TrustTier.VOUCHED: 0.85,
    TrustTier.REPUTABLE: 0.75,
    TrustTier.OPEN: 0.50,
    TrustTier.BLOCKED: 0.0,
}
# An un-tiered source (no tier could be resolved at all) gets the same prior as the open web — never
# higher. Derived from the OPEN prior so the two can't silently diverge when T2 tunes the blend.
_UNTIERED_PRIOR = _DEFAULT_PRIORS[TrustTier.OPEN]


class CredibilityScorer:
    """Scores a candidate source's credibility from its authority tier (P6.2, the §4b seam).

    Walking-skeleton scope: resolve the source's trust tier from the editable ``source_authorities``
    config (a SPINE/DENYLIST domain hit sets the prior; an already-tiered source — e.g. a VOUCHED
    manual upload — keeps its tier) and map that tier to a base credibility. PACK authorities are
    field-scoped and only apply once a run's ``SubjectField`` is plumbed through (T2/T3), so they
    are not applied here. The blended signals (recency, extraction, KC-relevance) layer on in T2;
    the risk-tiered trust floor that *uses* the score is T3.

    The authority table is read once and cached for the scorer's lifetime — one scorer per build run
    (the plan's "cached per run"), so the lazy load needs no lock.
    """

    def __init__(
        self,
        authorities: ISourceAuthorityStore,
        *,
        priors: Mapping[TrustTier, float] = _DEFAULT_PRIORS,
    ) -> None:
        self._authorities = authorities
        self._priors = priors
        self._index: dict[str, SourceAuthority] | None = None

    async def score(self, source: CandidateSource) -> ScoredSource:
        tier = await self._resolve_tier(source)
        credibility = (
            self._priors.get(tier, _UNTIERED_PRIOR) if tier is not None else _UNTIERED_PRIOR
        )
        logger.debug(
            "source_credibility_scored",
            kc_id=source.kc_id,
            tier=tier.value if tier is not None else None,
            credibility=credibility,
        )
        return ScoredSource(trust_tier=tier, credibility=credibility)

    async def _resolve_tier(self, source: CandidateSource) -> TrustTier | None:
        # A source acquired with a tier (a VOUCHED manual upload, an auto-discovery classification)
        # keeps it — the user's vouch is authoritative and is never downgraded by a table lookup.
        if source.trust_tier is not None:
            return source.trust_tier
        if not source.url:
            return None
        authority = self._lookup(host(source.url), await self._ensure_index())
        if authority is not None:
            return authority.trust_tier
        # No curated row: fall back to the deterministic, in-code classifier — gov/standards →
        # OFFICIAL, academic → REPUTABLE, a denylisted domain or an internal IP (the SSRF guard) →
        # BLOCKED, the rest → OPEN. So an authoritative domain is recognised before it is curated,
        # and the security boundary stays in pure code rather than depending on a DB read.
        return classify_domain(source.url)

    async def _ensure_index(self) -> dict[str, SourceAuthority]:
        """Load + index the authorities by domain on first use (cached for the scorer's lifetime).

        Only SPINE and DENYLIST (global) authorities are indexed: a PACK is field-scoped and must
        not promote a source outside its field, so it stays inactive until field context arrives.
        Returns the index (also cached on the instance) so callers get a narrowed type, no assert.
        """
        if self._index is None:
            self._index = {
                a.domain: a
                for a in await self._authorities.list_all()
                if a.kind is not AuthorityKind.PACK
            }
        return self._index

    @staticmethod
    def _lookup(domain: str, index: Mapping[str, SourceAuthority]) -> SourceAuthority | None:
        """Match a host to an authority by exact domain or as a subdomain of one (news.bbc.co.uk →
        bbc.co.uk). The longest matching suffix wins, so a subdomain prior beats its parent's."""
        if not domain:
            return None
        if domain in index:
            return index[domain]
        candidates = [a for d, a in index.items() if domain.endswith(f".{d}")]
        if not candidates:
            return None
        return max(candidates, key=lambda a: len(a.domain))
