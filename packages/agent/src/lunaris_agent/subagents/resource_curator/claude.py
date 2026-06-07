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
    passes_video_guards,
    video_quality_score,
)
from lunaris_runtime.resilience import build_anthropic_chat_model, retry_on_rate_limit
from lunaris_runtime.schema import CourseBrief, Modality, Module, Resource, ResourceKind, TrustTier

from .candidate_view import CandidateView
from .curation import CuratedResources
from .deterministic import DeterministicQueryTranslator
from .parser import CurationChoice, parse_curation
from .prompt import build_curation_prompt
from .search_query import SearchQuery
from .translator import IQueryTranslator

logger = structlog.get_logger()

# Over-retrieve, then judge down to the budget (CQ Phase 2 T2): a richer pool per query lets the
# content judge pick genuinely-fitting resources instead of settling for the first few hits.
_RESULTS_PER_QUERY = 12
_DEFAULT_BUDGET = ResourceBudget()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _blend_credibility(judge: float, quality: float | None) -> float:
    """Blend the judge's content credibility with the deterministic metric quality (CQ Phase 2 T4).

    Content is primary, so the judge dominates; the video metric is a bounded weight that nudges it.
    Candidates with no metric (non-video, or unenriched) keep the judge's score unchanged.
    """
    if quality is None:
        return judge
    return round(min(1.0, 0.7 * judge + 0.3 * quality), 2)


@dataclass(frozen=True)
class _Candidate:
    """A found resource candidate + its deterministically-classified trust tier, awaiting the judge.

    Trust is classified here (not by the model) and attached AFTER selection, so the relevance judge
    stays blind to the label (§15) while the user still sees a vetted tier. The content fields
    (``snippet`` from the result, plus ``good_result_looks_like`` + ``level_hint`` carried from the
    query) let the judge score CONTENT + level, not the title (CQ Phase 2 T2).
    """

    kind: ResourceKind
    url: str
    title: str
    source: str
    trust_tier: TrustTier
    duration: str = ""
    author: str = ""
    snippet: str = ""
    good_result_looks_like: str = ""
    level_hint: str = ""
    quality: float | None = None  # deterministic video metric score (T4); None for non-video


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
            for candidate in await self._candidates_for(search_query):
                if not candidate.url or candidate.url in seen:
                    continue
                seen.add(candidate.url)
                if candidate.trust_tier is not TrustTier.BLOCKED:
                    candidates.append(candidate)
        return candidates

    async def _candidates_for(self, search_query: SearchQuery) -> list[_Candidate]:
        """Find candidates for one query — videos via the IVideoSource, the rest via search.

        Each candidate carries the query's content signal (``good_result_looks_like`` + ``level``)
        and the result's ``snippet`` so the judge can score CONTENT + level (CQ Phase 2 T2).
        """
        if search_query.kind is ResourceKind.VIDEO:
            videos = await self._safe_find(search_query.query)
            return [
                _Candidate(
                    kind=search_query.kind,
                    url=video.url,
                    title=video.title,
                    source=host(video.url),
                    trust_tier=classify_domain(video.url),
                    duration=video.duration,
                    author=video.channel,
                    snippet=video.description,
                    good_result_looks_like=search_query.good_result_looks_like,
                    level_hint=search_query.level_hint,
                    quality=video_quality_score(video),
                )
                # Drop the unplayable up front (the gate's hard guard, T4); soft quality signals
                # ride along as `quality` and weight the kept resource's credibility.
                for video in videos
                if passes_video_guards(video)
            ]
        results = await self._safe_search(search_query.query)
        return [
            _Candidate(
                kind=search_query.kind,
                url=result.url,
                title=result.title,
                source=host(result.url),
                trust_tier=classify_domain(result.url),
                snippet=result.snippet,
                good_result_looks_like=search_query.good_result_looks_like,
                level_hint=search_query.level_hint,
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
        """The judge's view of each candidate — content + level signals, NOT the tier (§15)."""
        return [
            CandidateView(
                index=index,
                kind=candidate.kind,
                title=candidate.title,
                source=candidate.source,
                url=candidate.url,
                snippet=candidate.snippet,
                good_result_looks_like=candidate.good_result_looks_like,
                level_hint=candidate.level_hint,
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
            # Blend the judge's content credibility with the deterministic video metric (T4).
            credibility=_blend_credibility(credibility, candidate.quality),
            fetched_at=fetched_at,
            duration=candidate.duration or None,
            author=candidate.author or None,
        )

    def _chat_model(self) -> BaseChatModel:
        if not isinstance(self._model, str):
            return self._model
        if self._client is None:
            self._client = build_anthropic_chat_model(self._model)
        return self._client
