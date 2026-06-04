from collections.abc import Mapping

import structlog
from lunaris_runtime.schema import AuthorityKind, TrustTier

from lunaris_grounding.authorities.authority import SourceAuthority
from lunaris_grounding.authorities.registry_protocol import IScholarlyRegistry
from lunaris_grounding.authorities.scored_source import ScoredSource
from lunaris_grounding.authorities.store_protocol import ISourceAuthorityStore
from lunaris_grounding.discovery.domain_trust import classify_domain, host
from lunaris_grounding.ingest.source import CandidateSource

logger = structlog.get_logger()

# The tier prior → a base credibility, the dominant signal in the §4b blend. Deliberately ordered: a
# user-vouched source sits just below an official body but above the general web, and a blocked
# domain scores zero. A source with no tier gets the open-web prior, never "trusted by omission".
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

# How far extraction quality may nudge the credibility of an OPEN-tier source: a clean, substantive
# page earns up to +this, a thin/boilerplate one as much less. Only the *uncertain* open web is
# nudged; a curated or vouched source's credibility is its tier prior, not second-guessed by shape.
_OPEN_NUDGE = 0.15
# The text length (chars) at which a source counts as fully "substantive" for the length factor of
# extraction quality; shorter sources score proportionally lower.
_SUBSTANTIVE_LEN = 500


class CredibilityScorer:
    """Scores a candidate source's credibility (P6.2, the §4b blend) before ingestion.

    A transparent, deterministic blend — not a black box — logged with its inputs so a low score is
    explainable. It resolves the source's trust tier (an already-tiered source like a VOUCHED manual
    upload keeps its tier; otherwise the editable ``source_authorities`` table, then a scholarly
    registry floor, then the in-code ``classify_domain`` label/SSRF heuristic), then blends:

    - **tier prior** — the dominant signal (a blocked domain scores zero outright).
    - **extraction quality** — a deterministic measure of the candidate text's substance, which
      nudges only the *uncertain* open web (a clean, long page earns more than a thin/boilerplate
      one); a curated or vouched tier is trusted as-is.

    Cross-source agreement is computed at verify time (it needs the retrieved set); recency and
    KC-relevance are deferred (no published-date producer yet; KC-relevance overlaps the retriever's
    verify-time cosine). PACK authorities stay inert until a run's field is plumbed through (T2/T3).

    The authority table is read once and cached for the scorer's lifetime (one per build run).
    """

    def __init__(
        self,
        authorities: ISourceAuthorityStore,
        *,
        registry: IScholarlyRegistry | None = None,
        priors: Mapping[TrustTier, float] = _DEFAULT_PRIORS,
    ) -> None:
        self._authorities = authorities
        # Optional: no registry means no scholarly floor (the no-key default). The composition root
        # injects the real one (OpenAlex, P6.3) or StubScholarlyRegistry — never instantiated here.
        self._registry = registry
        self._priors = priors
        self._index: dict[str, SourceAuthority] | None = None

    async def score(self, source: CandidateSource) -> ScoredSource:
        tier = await self._resolve_tier(source)
        quality = _extraction_quality(source.text)
        credibility = self._blend(tier, quality)
        logger.debug(
            "source_credibility_scored",
            kc_id=source.kc_id,
            tier=tier.value if tier is not None else None,
            extraction_quality=round(quality, 3),
            credibility=round(credibility, 3),
        )
        return ScoredSource(trust_tier=tier, credibility=credibility)

    async def _resolve_tier(self, source: CandidateSource) -> TrustTier | None:
        # A source acquired with a tier (a VOUCHED manual upload, an auto-discovery classification)
        # keeps it — the user's vouch is authoritative and is never downgraded by a table lookup.
        if source.trust_tier is not None:
            return source.trust_tier
        url = source.url
        if not url:
            return None
        authority = self._lookup(host(url), await self._ensure_index())
        if authority is not None:
            return authority.trust_tier
        # No curated row: the deterministic in-code classifier — gov/standards → OFFICIAL, academic
        # → REPUTABLE, a denylisted domain or internal IP (SSRF guard) → BLOCKED, the rest → OPEN.
        tier = classify_domain(url)
        # An unknown (open-web) domain that the scholarly registry confirms is a real peer-reviewed
        # record is floored to REPUTABLE — an unknown host serving a real paper is not "open web".
        if (
            tier is TrustTier.OPEN
            and self._registry is not None
            and await self._registry.lookup(url) is not None
        ):
            return TrustTier.REPUTABLE
        return tier

    def _blend(self, tier: TrustTier | None, extraction_quality: float) -> float:
        """Return a credibility in [0, 1] from the tier prior + extraction quality.

        A curated or vouched tier is trusted at its prior — we don't second-guess a curator's
        judgment by page shape. Only the *uncertain* open web (or a fully un-tiered source) is
        nudged by extraction quality, so a substantive unknown source can rise above the 0.50 prior
        and a thin/boilerplate one falls below it. A blocked source earns nothing, however clean.
        """
        if tier is TrustTier.BLOCKED:
            return 0.0
        prior = self._priors.get(tier, _UNTIERED_PRIOR) if tier is not None else _UNTIERED_PRIOR
        if tier is not None and tier is not TrustTier.OPEN:
            return prior
        # Re-center quality [0, 1] around the midpoint, scaled to [-1, +1], so a midpoint extraction
        # is zero nudge and the extremes move the prior by the full _OPEN_NUDGE either way.
        quality_deviation = (extraction_quality - 0.5) * 2
        return max(0.0, min(1.0, prior + _OPEN_NUDGE * quality_deviation))

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


def _extraction_quality(text: str) -> float:
    """A deterministic [0, 1] proxy for how clean + substantive an extracted source is (§4b).

    Two transparent factors multiplied: length adequacy (ramps to 1 as the text reaches a
    substantive size) and content ratio (the fraction of characters that are letters or spaces, so a
    page that is mostly nav symbols / boilerplate punctuation scores low). Real article text scores
    high; a thin stub or a nav-sludge scrape scores low. Empty text scores 0.
    """
    stripped = text.strip()
    if not stripped:
        return 0.0
    length_score = min(len(stripped) / _SUBSTANTIVE_LEN, 1.0)
    content_ratio = sum(c.isalpha() or c.isspace() for c in stripped) / len(stripped)
    return length_score * content_ratio
