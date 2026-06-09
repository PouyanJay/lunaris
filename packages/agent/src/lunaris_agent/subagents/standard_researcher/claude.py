from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_grounding import (
    ExtractedContent,
    IContentExtractor,
    ISearchProvider,
    ResearchBudget,
    SearchResult,
    classify_domain,
    research_budget_for_brief,
)
from lunaris_runtime.resilience import (
    build_chat_model,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import (
    CourseBrief,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
    TrustTier,
)

from .distillation import Distillation
from .outcome import ResearchOutcome
from .parser import parse_distillation
from .prompt import build_research_prompt
from .query import build_research_queries
from .seed_source import SeedSource

logger = structlog.get_logger()

# How many hits to ask for per query; the per-build BUDGET (search + fetch counts) does the real
# bounding. Candidates are preferred highest-trust-first, so a small fetch budget keeps the best.
_RESULTS_PER_QUERY = 5
_TIER_RANK: dict[TrustTier, int] = {
    TrustTier.OFFICIAL: 0,
    TrustTier.REPUTABLE: 1,
    TrustTier.OPEN: 2,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class _Candidate:
    """A search hit + its classified trust tier, carried through fetch into the provenance."""

    result: SearchResult
    tier: TrustTier


@dataclass(frozen=True)
class _FetchedPage:
    """A fetched candidate: its extracted content + the instant it was acquired (its provenance)."""

    candidate: _Candidate
    content: ExtractedContent
    fetched_at: str


class ClaudeStandardResearcher:
    """Live standard researcher: deterministic search + fetch, one Claude distillation, provenance.

    Builds narrow queries from the brief, searches them via the shared ``ISearchProvider``, then
    classifies each hit's trust tier, drops blocked domains, prefers the highest-trust candidates,
    and fetches + extracts the top of them via the shared ``IContentExtractor`` (within the budget),
    asking the model to distil the real competency descriptors + score lines from the fetched text.
    Every accepted page becomes a ``ResearchSource`` stamped with its ``fetched_at`` + trust tier at
    acquisition (structural provenance). Best-effort throughout: a search/fetch failure or an empty
    distillation degrades to PARTIAL/UNAVAILABLE, never an exception that breaks the build.

    ``model`` is a model id (lazy ``ChatAnthropic``, the worker tier) or an injected chat model
    (tests). ``clock`` stamps ``fetched_at`` and is injectable so provenance is deterministic too.
    """

    def __init__(
        self,
        model: str | BaseChatModel,
        search: ISearchProvider,
        extractor: IContentExtractor,
        *,
        budget: ResearchBudget | None = None,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        self._model = model
        self._client: BaseChatModel | None = None
        self._search = search
        self._extractor = extractor
        # None → size the budget to each brief at research time (CQ Phase 1.2's depth policy); an
        # explicit budget is a pre-authorized depth ceiling for callers that already know it.
        self._budget = budget
        self._clock = clock

    async def research(self, brief: CourseBrief) -> ResearchOutcome:
        """Adaptively ground the brief: plan queries → search → fetch → distil a structured
        framework → deepen on the model's follow-up queries, until coverage is met, the round
        ceiling is hit, or the search/fetch budget runs out (CQ Phase 1.1). The budget is sized to
        the brief (CQ Phase 1.2) unless one was injected."""
        budget = self._budget if self._budget is not None else research_budget_for_brief(brief)
        fetched: list[_FetchedPage] = []
        seen: set[str] = set()
        queries = build_research_queries(brief)
        remaining_searches = budget.max_searches
        remaining_fetches = budget.max_fetches
        distillation = Distillation()
        rounds = 0
        for _ in range(budget.max_rounds):
            round_queries = queries[:remaining_searches]
            if not round_queries or remaining_fetches <= 0:
                break
            remaining_searches -= len(round_queries)
            candidates = (await self._gather(brief, round_queries, seen))[:remaining_fetches]
            # Charge the budget per fetch ATTEMPT (the cost ceiling), not per usable page, so sites
            # that reliably fail to extract can't be re-tried until the budget is silently drained.
            remaining_fetches -= len(candidates)
            fetched.extend(await self._fetch(candidates))
            if not fetched:
                # Nothing readable yet and no distillation to propose follow-ups — degrade honestly
                # rather than calling the model on no evidence.
                break
            rounds += 1
            distillation = await self._distil(brief, [page.content for page in fetched])
            queries = distillation.follow_up_queries  # deepen on the gaps the model flagged

        if not fetched:
            logger.info("standard_research_unavailable", goal=brief.goal)
            return ResearchOutcome(research=StandardResearch(status=ResearchStatus.UNAVAILABLE))

        sources = self._build_sources(fetched)
        # COMPLETE only when the sources actually yielded competencies; sources-but-nothing-found
        # is honest PARTIAL (the schema invariant guarantees COMPLETE always cites a source).
        status = ResearchStatus.COMPLETE if distillation.competencies else ResearchStatus.PARTIAL
        logger.info(
            "standard_research_completed",
            goal=brief.goal,
            status=status.value,
            rounds=rounds,
            area_count=len(distillation.areas),
            competency_count=len(distillation.competencies),
            source_count=len(sources),
        )
        research = StandardResearch(
            status=status,
            areas=distillation.areas,
            competencies=distillation.competencies,
            score_table=distillation.score_table,
            sources=sources,
        )
        # The same fetched pages that grounded the brief seed the corpus (P6.4): carry their text
        # forward so the SEED feed ingests already-paid-for evidence rather than re-fetching.
        return ResearchOutcome(research=research, seeds=self._build_seeds(fetched))

    async def _gather(
        self, brief: CourseBrief, queries: list[str], seen: set[str]
    ) -> list[_Candidate]:
        """Search the round's queries, classify each hit, drop blocked, prefer highest-trust first.

        De-duplicates by URL across rounds via ``seen`` (mutated here); the caller truncates to the
        remaining fetch budget so the round spends it on the most authoritative sources.
        """
        authority = brief.target_standard.authority_hint if brief.target_standard else ""
        candidates: list[_Candidate] = []
        for query in queries:
            for result in await self._safe_search(query):
                if not result.url or result.url in seen:
                    continue
                seen.add(result.url)
                tier = classify_domain(result.url, authority)
                if tier is not TrustTier.BLOCKED:
                    candidates.append(_Candidate(result, tier))
        # .get with a past-the-end default keeps the sort total if TrustTier ever gains a member.
        candidates.sort(key=lambda candidate: _TIER_RANK.get(candidate.tier, len(_TIER_RANK)))
        return candidates

    async def _safe_search(self, query: str) -> list[SearchResult]:
        try:
            return await self._search.search(query, max_results=_RESULTS_PER_QUERY)
        except Exception:
            logger.warning("standard_research_search_failed", query=query, exc_info=True)
            return []

    async def _fetch(self, candidates: list[_Candidate]) -> list[_FetchedPage]:
        """Fetch + extract each candidate, stamping its fetched_at at acquisition.

        Keeps only pages with usable text (best-effort); the carried timestamp is the provenance
        instant, set the moment the page is read — not later when sources are assembled.
        """
        fetched: list[_FetchedPage] = []
        for candidate in candidates:
            content = await self._safe_extract(candidate.result.url)
            if content is not None and content.text.strip():
                fetched.append(_FetchedPage(candidate, content, self._clock()))
        return fetched

    async def _safe_extract(self, url: str) -> ExtractedContent | None:
        try:
            return await self._extractor.extract(url)
        except Exception:
            logger.warning("standard_research_extract_failed", url=url, exc_info=True)
            return None

    async def _distil(self, brief: CourseBrief, pages: list[ExtractedContent]) -> Distillation:
        """Ask the model to distil a structured framework + follow-up queries from the fetched pages
        (one call per round, re-distilling over all pages read so far)."""
        prompt = build_research_prompt(brief, pages)
        message = await retry_on_rate_limit(lambda: self._chat_model().ainvoke(prompt))
        raw = message.content if isinstance(message.content, str) else str(message.content)
        return parse_distillation(raw)

    @staticmethod
    def _build_sources(fetched: list[_FetchedPage]) -> list[ResearchSource]:
        """Assemble the provenance: one ResearchSource per fetched page, stamped at acquisition."""
        return [
            ResearchSource(
                url=page.candidate.result.url,
                title=page.content.title or page.candidate.result.title,
                trust_tier=page.candidate.tier,
                fetched_at=page.fetched_at,
            )
            for page in fetched
        ]

    @staticmethod
    def _build_seeds(fetched: list[_FetchedPage]) -> tuple[SeedSource, ...]:
        """Carry the already-fetched page text forward as corpus seed material (P6.4).

        One SeedSource per fetched page, keeping the extracted text + its acquisition-time tier and
        timestamp. Credibility is left unset on purpose — the ingestor's scorer grades each seed
        through the same gate as every other source, so a seed earns its place rather than
        inheriting trust from having been read during research.
        """
        return tuple(
            SeedSource(
                url=page.candidate.result.url,
                text=page.content.text,
                title=page.content.title or page.candidate.result.title,
                trust_tier=page.candidate.tier,
                fetched_at=page.fetched_at,
            )
            for page in fetched
        )

    def _chat_model(self) -> BaseChatModel:
        if not isinstance(self._model, str):
            return self._model
        if self._client is None:
            self._client = build_chat_model(self._model)
        return self._client
