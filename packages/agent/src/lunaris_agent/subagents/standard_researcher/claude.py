from collections.abc import Callable
from datetime import UTC, datetime

import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_grounding import (
    ExtractedContent,
    IContentExtractor,
    ISearchProvider,
    SearchResult,
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

from .parser import parse_research
from .prompt import build_research_prompt
from .query import build_research_queries

logger = structlog.get_logger()

# Bounded best-effort: cap how wide we search + how many pages we fetch per build, so an always-on
# research step can't run away. P7.2-T2 replaces these constants with an injected ResearchBudget.
_MAX_RESULTS_PER_QUERY = 5
_MAX_FETCHES = 4


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ClaudeStandardResearcher:
    """Live standard researcher: deterministic search + fetch, one Claude distillation, provenance.

    Builds narrow queries from the brief, searches them via the shared ``ISearchProvider``, fetches
    + extracts the top candidates via the shared ``IContentExtractor`` (bounded), and asks the model
    to distil the real competency descriptors + score lines from the fetched text. Every accepted
    page becomes a ``ResearchSource`` stamped with its ``fetched_at`` + trust tier at acquisition
    (structural provenance). Best-effort throughout: a search/fetch failure or an empty distillation
    degrades to PARTIAL/UNAVAILABLE, never an exception that breaks the build.

    ``model`` is a model id (lazy ``ChatAnthropic``, the worker tier) or an injected chat model
    (tests). ``clock`` stamps ``fetched_at`` and is injectable so provenance is deterministic too.
    """

    def __init__(
        self,
        model: str | BaseChatModel,
        search: ISearchProvider,
        extractor: IContentExtractor,
        *,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        self._model = model
        self._client: BaseChatModel | None = None
        self._search = search
        self._extractor = extractor
        self._clock = clock

    async def research(self, brief: CourseBrief) -> StandardResearch:
        fetched = await self._fetch(await self._gather_candidates(build_research_queries(brief)))
        if not fetched:
            logger.info("standard_research_unavailable", goal=brief.goal)
            return StandardResearch(status=ResearchStatus.UNAVAILABLE)

        competencies, score_table = await self._distil(brief, [page for _r, page, _t in fetched])
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
        return StandardResearch(
            status=status, competencies=competencies, score_table=score_table, sources=sources
        )

    async def _distil(
        self, brief: CourseBrief, pages: list[ExtractedContent]
    ) -> tuple[list[str], list[str]]:
        """Ask the model to distil competencies + score lines from the fetched pages (one call)."""
        prompt = build_research_prompt(brief, pages)
        message = await retry_on_rate_limit(lambda: self._chat_model().ainvoke(prompt))
        raw = message.content if isinstance(message.content, str) else str(message.content)
        return parse_research(raw)

    @staticmethod
    def _build_sources(
        fetched: list[tuple[SearchResult, ExtractedContent, str]],
    ) -> list[ResearchSource]:
        """Assemble the provenance: one ResearchSource per fetched page, stamped at acquisition."""
        return [
            ResearchSource(
                url=result.url,
                title=page.title or result.title,
                trust_tier=TrustTier.OPEN,
                fetched_at=fetched_at,
            )
            for result, page, fetched_at in fetched
        ]

    async def _gather_candidates(self, queries: list[str]) -> list[SearchResult]:
        """Search every query, de-duplicating by URL (first hit wins), best-effort per query."""
        seen: set[str] = set()
        candidates: list[SearchResult] = []
        for query in queries:
            for result in await self._safe_search(query):
                if result.url and result.url not in seen:
                    seen.add(result.url)
                    candidates.append(result)
        return candidates

    async def _safe_search(self, query: str) -> list[SearchResult]:
        try:
            return await self._search.search(query, max_results=_MAX_RESULTS_PER_QUERY)
        except Exception:
            logger.warning("standard_research_search_failed", query=query, exc_info=True)
            return []

    async def _fetch(
        self, candidates: list[SearchResult]
    ) -> list[tuple[SearchResult, ExtractedContent, str]]:
        """Fetch + extract up to the budget, stamping each page's fetched_at at acquisition.

        Keeps only pages with usable text (best-effort); the carried timestamp is the provenance
        instant, set the moment the page is read — not later when sources are assembled.
        """
        fetched: list[tuple[SearchResult, ExtractedContent, str]] = []
        for result in candidates[:_MAX_FETCHES]:
            page = await self._safe_extract(result.url)
            if page is not None and page.text.strip():
                fetched.append((result, page, self._clock()))
        return fetched

    async def _safe_extract(self, url: str) -> ExtractedContent | None:
        try:
            return await self._extractor.extract(url)
        except Exception:
            logger.warning("standard_research_extract_failed", url=url, exc_info=True)
            return None

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
