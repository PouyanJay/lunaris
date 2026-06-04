"""The discovery loop as a deterministic LangGraph sub-graph (P6.3).

Mirrors ``authoring/loop.py``: a ``StateGraph`` with exact control flow, run behind the single
``discover_grounding`` tool call. The agent reasons about *when* to ground; this loop owns *how* —

  plan → search → fetch+extract → gate (score + blind relevance judge) → ingest

The control guarantees stay in code, not the model: queries are planned deterministically from the
curriculum (subject-keyed, never claim-keyed), each fetched source is graded by the deterministic
credibility scorer, and an off-topic source is dropped by an injected judge kept **blind to the
source's trust label**. The author never selects its own evidence; discovery never ingests a page
just because it ranked well. Every node streams its work onto the run's agent channel (the event tap
can't see inside the tool), so the build canvas shows the queries, fetches, and per-source verdicts
live. A reflect/coverage cycle (not yet implemented) will add one conditional edge back to ``plan``.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from lunaris_grounding import (
    CandidateSource,
    CorpusIngestor,
    ExtractedContent,
    IContentExtractor,
    ICredibilityScorer,
    ISearchProvider,
    ResearchBudget,
    ScoredSource,
    SearchResult,
    classify_domain,
    host,
)
from lunaris_runtime.schema import (
    AcquisitionMode,
    AgentEventKind,
    SourceEvaluation,
    SourceType,
    TrustTier,
)

from ..draft import CourseDraft
from .queries import DiscoveryQuery, build_discovery_queries
from .relevance_judge import IRelevanceJudge, RelevanceVerdict

logger = structlog.get_logger()

_RESULTS_PER_QUERY = 5
# Moderate per-build caps. A soft cap that asks the human before going further (rather than a hard
# ceiling) is the intended model; here the budget simply bounds a single pass.
_DEFAULT_BUDGET = ResearchBudget(max_searches=10, max_fetches=14)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _source_id(course_id: str, url: str) -> str:
    """A stable per-(course, URL) id so re-discovering the same page upserts, not duplicates."""
    digest = hashlib.sha256(f"{course_id}|{url}".encode()).hexdigest()[:16]
    return f"auto:{course_id}:{digest}"


@dataclass(frozen=True)
class _Candidate:
    """A search hit kept for fetching, tagged with the concept whose query surfaced it."""

    result: SearchResult
    kc_id: str


@dataclass(frozen=True)
class _Fetched:
    """A fetched candidate: its extracted content + the instant it was acquired (its provenance)."""

    candidate: _Candidate
    content: ExtractedContent
    fetched_at: str


class DiscoveryState(TypedDict, total=False):
    """The loop's working state, threaded between nodes (in-process; no checkpointer)."""

    queries: list[DiscoveryQuery]
    candidates: list[_Candidate]
    fetched: list[_Fetched]
    accepted: list[CandidateSource]
    chunks_ingested: int
    covered_kcs: list[str]


def build_discovery_subgraph(
    search: ISearchProvider,
    extractor: IContentExtractor,
    scorer: ICredibilityScorer,
    judge: IRelevanceJudge,
    ingestor: CorpusIngestor,
    draft: CourseDraft,
    *,
    budget: ResearchBudget = _DEFAULT_BUDGET,
    clock: Callable[[], str] = _utc_now_iso,
) -> CompiledStateGraph:
    """Compile the plan → search → fetch → gate → ingest loop over ``draft``'s concepts.

    Closed over the run draft so the sources it ingests land in exactly the corpus the verifier will
    retrieve from (course-scoped). Returns a compiled graph the ``discover_grounding`` tool invokes.
    """
    concepts_by_id = {kc.id: kc for kc in draft.concepts}

    async def plan_node(_state: DiscoveryState) -> DiscoveryState:
        queries = build_discovery_queries(draft)[: budget.max_searches]
        await draft.agent.emit(
            AgentEventKind.TODO,
            todos=[{"content": f"Search: {query.text}", "status": "pending"} for query in queries],
        )
        await draft.agent.emit(
            AgentEventKind.REASONING,
            text=f"Planned {len(queries)} search(es) across the curriculum's concepts.",
        )
        return {"queries": queries}

    async def search_node(state: DiscoveryState) -> DiscoveryState:
        seen: set[str] = set()
        candidates: list[_Candidate] = []
        for query in state.get("queries", []):
            await draft.agent.emit(
                AgentEventKind.TOOL_CALL, tool="search", tool_args={"query": query.text}
            )
            results = await _safe_search(query.text)
            await draft.agent.emit(
                AgentEventKind.TOOL_RESULT,
                tool="search",
                result=f"{len(results)} hit(s) for “{query.text}”",
            )
            for result in results:
                if not result.url or result.url in seen:
                    continue
                seen.add(result.url)
                # Drop denylisted / SSRF hosts before paying to fetch them.
                if classify_domain(result.url) is TrustTier.BLOCKED:
                    continue
                candidates.append(_Candidate(result, query.kc_id))
        return {"candidates": candidates[: budget.max_fetches]}

    async def fetch_node(state: DiscoveryState) -> DiscoveryState:
        fetched: list[_Fetched] = []
        for candidate in state.get("candidates", []):
            await draft.agent.emit(
                AgentEventKind.TOOL_CALL, tool="fetch", tool_args={"url": candidate.result.url}
            )
            content = await _safe_extract(candidate.result.url)
            has_text = content is not None and bool(content.text.strip())
            await draft.agent.emit(
                AgentEventKind.TOOL_RESULT,
                tool="fetch",
                result=("extracted" if has_text else "no usable text")
                + f" — {candidate.result.url}",
            )
            if has_text and content is not None:
                fetched.append(_Fetched(candidate, content, clock()))
        return {"fetched": fetched}

    async def gate_node(state: DiscoveryState) -> DiscoveryState:
        accepted: list[CandidateSource] = []
        for page in state.get("fetched", []):
            source = _to_source(page)
            scored = await scorer.score(source)
            if scored.trust_tier is TrustTier.BLOCKED:
                await _emit_evaluated(page, scored, accepted=False, reason="Blocked source.")
                continue
            verdict = await _judge(page)
            if not verdict.relevant:
                await _emit_evaluated(page, scored, accepted=False, reason=verdict.reason)
                continue
            accepted.append(
                replace(source, trust_tier=scored.trust_tier, credibility=scored.credibility)
            )
            await _emit_evaluated(page, scored, accepted=True, reason=verdict.reason)
        return {"accepted": accepted}

    async def ingest_node(state: DiscoveryState) -> DiscoveryState:
        accepted = state.get("accepted", [])
        chunks = await ingestor.ingest(accepted, run_id=draft.run_id) if accepted else 0
        covered = sorted({source.kc_id for source in accepted})
        await draft.agent.emit(
            AgentEventKind.REASONING,
            text=f"Ingested {chunks} grounding chunk(s) covering {len(covered)} concept(s).",
        )
        return {"chunks_ingested": chunks, "covered_kcs": covered}

    async def _safe_search(query: str) -> list[SearchResult]:
        try:
            return await search.search(query, max_results=_RESULTS_PER_QUERY)
        except Exception:
            logger.warning("discovery_search_failed", query=query, exc_info=True)
            return []

    async def _safe_extract(url: str) -> ExtractedContent | None:
        try:
            return await extractor.extract(url)
        except Exception:
            logger.warning("discovery_extract_failed", url=url, exc_info=True)
            return None

    async def _judge(page: _Fetched) -> RelevanceVerdict:
        kc = concepts_by_id.get(page.candidate.kc_id)
        return await judge.is_relevant(
            kc_label=kc.label if kc else page.candidate.kc_id,
            kc_definition=kc.definition if kc else "",
            text=page.content.text,
        )

    def _to_source(page: _Fetched) -> CandidateSource:
        url = page.candidate.result.url
        return CandidateSource(
            kc_id=page.candidate.kc_id,
            text=page.content.text,
            title=page.content.title or page.candidate.result.title or None,
            url=url,
            source_type=SourceType.WEB,
            fetched_at=page.fetched_at,
            acquisition_mode=AcquisitionMode.AUTO,
            course_id=draft.course_id,
            source_id=_source_id(draft.course_id, url),
        )

    async def _emit_evaluated(
        page: _Fetched, scored: ScoredSource, *, accepted: bool, reason: str
    ) -> None:
        await draft.agent.emit(
            AgentEventKind.SOURCE_EVALUATED,
            source=SourceEvaluation(
                kc_id=page.candidate.kc_id,
                domain=host(page.candidate.result.url),
                trust_tier=scored.trust_tier,
                credibility=scored.credibility,
                source_type=SourceType.WEB,
                accepted=accepted,
                reason=reason,
            ),
        )

    graph: StateGraph = StateGraph(DiscoveryState)
    graph.add_node("plan", plan_node)
    graph.add_node("search", search_node)
    graph.add_node("fetch", fetch_node)
    graph.add_node("gate", gate_node)
    graph.add_node("ingest", ingest_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "fetch")
    graph.add_edge("fetch", "gate")
    graph.add_edge("gate", "ingest")
    graph.add_edge("ingest", END)
    return graph.compile()
