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
)
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import (
    CourseBrief,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
    TrustTier,
)

from .outcome import ResearchOutcome
from .parser import parse_research
from .prompt import build_research_prompt
from .query import build_research_queries
from .seed_source import SeedSource

logger = structlog.get_logger()

# How many hits to ask for per query; the per-build BUDGET (search + fetch counts) does the real
# bounding. Candidates are preferred highest-trust-first, so a small fetch budget keeps the best.
_RESULTS_PER_QUERY = 5
_DEFAULT_BUDGET = ResearchBudget()
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
        budget: ResearchBudget = _DEFAULT_BUDGET,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        self._model = model
        self._client: BaseChatModel | None = None
        self._search = search
        self._extractor = extractor
        self._budget = budget
        self._clock = clock

    async def research(self, brief: CourseBrief) -> ResearchOutcome:
        fetched = await self._fetch(await self._gather_candidates(brief))
        if not fetched:
            logger.info("standard_research_unavailable", goal=brief.goal)
            return ResearchOutcome(research=StandardResearch(status=ResearchStatus.UNAVAILABLE))

        competencies, score_table = await self._distil(brief, [p.content for p in fetched])
        sources = self._build_sources(fetched)
        # COMPLETE only when the sources actually yielded competencies; sources-but-nothing-found
        # is honest PARTIAL (the schema invariant guarantees COMPLETE always cites a source).
        status = ResearchStatus.COMPLETE if competencies else ResearchStatus.PARTIAL
        logger.info(
            "standard_research_completed",
            goal=brief.goal,
            status=status.value,
            competency_count=len(competencies),
            source_count=len(sources),
        )
        research = StandardResearch(
            status=status, competencies=competencies, score_table=score_table, sources=sources
        )
        # The same fetched pages that grounded the brief seed the corpus (P6.4): carry their text
        # forward so the SEED feed ingests already-paid-for evidence rather than re-fetching.
        return ResearchOutcome(research=research, seeds=self._build_seeds(fetched))

    async def _gather_candidates(self, brief: CourseBrief) -> list[_Candidate]:
        """Search (within the budget), classify each hit, drop blocked, prefer highest-trust first.

        Returns the top ``max_fetches`` candidates so the fetch step spends its budget on the most
        authoritative sources; de-duplicated by URL, best-effort per query.
        """
        queries = build_research_queries(brief)[: self._budget.max_searches]
        authority = brief.target_standard.authority_hint if brief.target_standard else ""
        seen: set[str] = set()
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
        return candidates[: self._budget.max_fetches]

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

    async def _distil(
        self, brief: CourseBrief, pages: list[ExtractedContent]
    ) -> tuple[list[str], list[str]]:
        """Ask the model to distil competencies + score lines from the fetched pages (one call)."""
        prompt = build_research_prompt(brief, pages)
        message = await retry_on_rate_limit(lambda: self._chat_model().ainvoke(prompt))
        raw = message.content if isinstance(message.content, str) else str(message.content)
        return parse_research(raw)

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
            from langchain_anthropic import ChatAnthropic

            self._client = ChatAnthropic(
                model=self._model,
                default_request_timeout=LLM_REQUEST_TIMEOUT_S,
                max_retries=LLM_MAX_RETRIES,
                rate_limiter=get_llm_rate_limiter(),
            )
        return self._client
