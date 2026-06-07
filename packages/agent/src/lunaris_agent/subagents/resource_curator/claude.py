from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from langchain_core.language_models import BaseChatModel
from lunaris_grounding import (
    ISearchProvider,
    IVideoSource,
    ResourceBudget,
    SearchResult,
    VideoResult,
    classify_domain,
    host,
)
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
    retry_on_rate_limit,
)
from lunaris_runtime.schema import CourseBrief, Modality, Module, Resource, ResourceKind, TrustTier

from .candidate_view import CandidateView
from .curation import CuratedResources
from .deterministic import DeterministicQueryTranslator
from .parser import CurationChoice, parse_curation
from .prompt import build_curation_prompt
from .translator import IQueryTranslator

logger = structlog.get_logger()

_RESULTS_PER_QUERY = 4
_DEFAULT_BUDGET = ResourceBudget()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class _Candidate:
    """A found resource candidate + its deterministically-classified trust tier, awaiting the judge.

    Trust is classified here (not by the model) and attached AFTER selection, so the relevance judge
    stays blind to the label (§15) while the user still sees a vetted tier.
    """

    kind: ResourceKind
    url: str
    title: str
    source: str
    trust_tier: TrustTier
    duration: str = ""
    author: str = ""


class ClaudeResourceCurator:
    """Live resource curator: deterministic search → trust-classify → one Claude relevance judge.

    Builds narrow per-kind queries from the module's competency, routes video queries to the
    ``IVideoSource`` and the rest to the shared ``ISearchProvider``, classifies each hit's trust
    tier (dropping blocked domains), then asks the model — blind to those tiers — to keep the
    candidates that fit the lesson, place each on a Merrill phase, and write a "why" + credibility.
    Kept resources are stamped with their trust tier + ``fetched_at`` at selection (structural
    provenance).
    Best-effort throughout: a search/judge failure or empty selection yields no resources, never an
    exception that breaks the build.

    ``model`` is a model id (lazy ``ChatAnthropic``, worker tier) or an injected chat model (tests);
    ``clock`` stamps ``fetched_at`` and is injectable so provenance is deterministic too.
    """

    def __init__(
        self,
        model: str | BaseChatModel,
        search: ISearchProvider,
        video_source: IVideoSource,
        *,
        translator: IQueryTranslator | None = None,
        budget: ResourceBudget = _DEFAULT_BUDGET,
        clock: Callable[[], str] = _utc_now_iso,
    ) -> None:
        self._model = model
        self._client: BaseChatModel | None = None
        self._search = search
        self._video_source = video_source
        self._translator = translator or DeterministicQueryTranslator()
        self._budget = budget
        self._clock = clock

    async def curate(
        self, module: Module, brief: CourseBrief | None = None, *, modality: Modality | None = None
    ) -> CuratedResources:
        candidates = await self._gather(module, brief, modality)
        if not candidates:
            return CuratedResources()
        prompt = build_curation_prompt(
            module, self._views(candidates), limit=self._budget.max_resources
        )
        choices = parse_curation(await self._judge(prompt))
        curated = self._assemble(candidates, choices)
        kept = len(curated.activate + curated.demonstrate + curated.apply + curated.integrate)
        logger.info("resources_curated", module=module.id, kept=kept, candidates=len(candidates))
        return curated

    def _assemble(
        self, candidates: list[_Candidate], choices: list[CurationChoice]
    ) -> CuratedResources:
        """Place the judge's kept candidates onto their chosen phases, within the resource budget.

        Stamps one ``fetched_at`` for the batch (provenance at selection), guards each choice's
        index against the candidate list, and stops once ``max_resources`` are kept (budget cap).
        """
        buckets: dict[str, list[Resource]] = {
            "activate": [],
            "demonstrate": [],
            "apply": [],
            "integrate": [],
        }
        fetched_at = self._clock()
        kept = 0
        for choice in choices:
            if kept >= self._budget.max_resources or not 0 <= choice.index < len(candidates):
                continue
            buckets[choice.phase].append(
                self._to_resource(
                    candidates[choice.index], choice.why, choice.credibility, fetched_at
                )
            )
            kept += 1
        return CuratedResources(**buckets)

    async def _gather(
        self, module: Module, brief: CourseBrief | None, modality: Modality | None
    ) -> list[_Candidate]:
        """Plan queries via the translator (within budget), classify trust, drop blocked + dupes."""
        queries = (await self._translator.translate(module, brief, modality=modality))[
            : self._budget.max_searches
        ]
        seen: set[str] = set()
        candidates: list[_Candidate] = []
        for search_query in queries:
            for candidate in await self._candidates_for(search_query.kind, search_query.query):
                if not candidate.url or candidate.url in seen:
                    continue
                seen.add(candidate.url)
                if candidate.trust_tier is not TrustTier.BLOCKED:
                    candidates.append(candidate)
        return candidates

    async def _candidates_for(self, kind: ResourceKind, query: str) -> list[_Candidate]:
        """Find candidates for one query — videos via the IVideoSource, the rest via search."""
        if kind is ResourceKind.VIDEO:
            videos = await self._safe_find(query)
            return [
                _Candidate(
                    kind=kind,
                    url=video.url,
                    title=video.title,
                    source=host(video.url),
                    trust_tier=classify_domain(video.url),
                    duration=video.duration,
                    author=video.channel,
                )
                for video in videos
            ]
        results = await self._safe_search(query)
        return [
            _Candidate(
                kind=kind,
                url=result.url,
                title=result.title,
                source=host(result.url),
                trust_tier=classify_domain(result.url),
            )
            for result in results
        ]

    async def _safe_search(self, query: str) -> list[SearchResult]:
        try:
            return await self._search.search(query, max_results=_RESULTS_PER_QUERY)
        except Exception:
            logger.warning("resource_search_failed", query=query, exc_info=True)
            return []

    async def _safe_find(self, query: str) -> list[VideoResult]:
        try:
            return await self._video_source.find(query, max_results=_RESULTS_PER_QUERY)
        except Exception:
            logger.warning("resource_video_search_failed", query=query, exc_info=True)
            return []

    async def _judge(self, prompt: str) -> str:
        try:
            message = await retry_on_rate_limit(lambda: self._chat_model().ainvoke(prompt))
        except Exception:
            logger.warning("resource_judge_failed", exc_info=True)
            return ""
        return message.content if isinstance(message.content, str) else str(message.content)

    @staticmethod
    def _views(candidates: list[_Candidate]) -> list[CandidateView]:
        """The judge's blind view of each candidate — kind/title/source/url, NOT the trust tier."""
        return [
            CandidateView(
                index=index,
                kind=candidate.kind,
                title=candidate.title,
                source=candidate.source,
                url=candidate.url,
            )
            for index, candidate in enumerate(candidates)
        ]

    @staticmethod
    def _to_resource(
        candidate: _Candidate, why: str, credibility: float, fetched_at: str
    ) -> Resource:
        return Resource(
            kind=candidate.kind,
            title=candidate.title,
            url=candidate.url,
            source=candidate.source,
            why=why,
            trust_tier=candidate.trust_tier,
            credibility=credibility,
            fetched_at=fetched_at,
            duration=candidate.duration or None,
            author=candidate.author or None,
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
