"""The discovery loop as a deterministic LangGraph sub-graph (P6.3).

Mirrors ``authoring/loop.py``: a ``StateGraph`` with exact control flow, run behind the single
``discover_grounding`` tool call. The agent reasons about *when* to ground; this loop owns *how* —

  plan → search → fetch+extract → gate (score + blind relevance judge) → ingest → reflect → …

The control guarantees stay in code, not the model: queries are planned deterministically from the
curriculum (subject-keyed, never claim-keyed), each fetched source is graded by the deterministic
credibility scorer, and an off-topic source is dropped by an injected judge kept **blind to the
source's trust label**. The author never selects its own evidence; discovery never ingests a page
just because it ranked well. The **reflect** node re-queries the concepts still short of
cross-source coverage (evidence from ``_MIN_DOMAINS_PER_KC`` independent domains), bounded by a
per-round budget + a max-round ceiling + a no-progress guard, so the loop converges or stops — it
never runs away. Every node streams its work onto the run's agent channel (the event tap can't see
inside the tool), so the build canvas shows the queries, fetches, and per-source verdicts live.
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
from .budget import DiscoveryBudget
from .queries import DiscoveryQuery, build_discovery_queries
from .relevance_judge import IRelevanceJudge, RelevanceVerdict

logger = structlog.get_logger()

_RESULTS_PER_QUERY = 5
# A concept is "covered" once accepted evidence corroborates it across this many independent domains
# — the cross-source agreement the verifier's HIGH-risk floor rewards. Below it, reflect re-queries.
_MIN_DOMAINS_PER_KC = 2
_DEFAULT_BUDGET = DiscoveryBudget()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _source_id(course_id: str, url: str) -> str:
    """A stable per-(course, URL) id so re-discovering the same page upserts, not duplicates."""
    digest = hashlib.sha256(f"{course_id}|{url}".encode()).hexdigest()[:16]
    return f"auto:{course_id}:{digest}"


def _uncovered(concept_ids: list[str], accepted: list[CandidateSource]) -> list[str]:
    """Concepts whose accepted evidence spans fewer than ``_MIN_DOMAINS_PER_KC`` domains."""
    domains: dict[str, set[str]] = {}
    for source in accepted:
        if source.url:
            domains.setdefault(source.kc_id, set()).add(host(source.url))
    return [kc_id for kc_id in concept_ids if len(domains.get(kc_id, set())) < _MIN_DOMAINS_PER_KC]


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
    """The loop's working state, threaded between nodes (in-process; no checkpointer).

    ``accepted``/``seen_urls``/``chunks_ingested`` accumulate across reflect rounds; ``round`` and
    ``prev_total`` (the accepted count at the round's start) drive the bounded cycle.
    """

    queries: list[DiscoveryQuery]
    candidates: list[_Candidate]
    fetched: list[_Fetched]
    round_accepted: list[CandidateSource]
    accepted: list[CandidateSource]
    seen_urls: list[str]
    chunks_ingested: int
    covered_kcs: list[str]
    round: int
    prev_total: int
    should_continue: bool


def build_discovery_subgraph(
    search: ISearchProvider,
    extractor: IContentExtractor,
    scorer: ICredibilityScorer,
    judge: IRelevanceJudge,
    ingestor: CorpusIngestor,
    draft: CourseDraft,
    *,
    budget: DiscoveryBudget = _DEFAULT_BUDGET,
    clock: Callable[[], str] = _utc_now_iso,
) -> CompiledStateGraph:
    """Compile the plan → search → fetch → gate → ingest → reflect loop over ``draft``'s concepts.

    Closed over the run draft so the sources it ingests land in exactly the corpus the verifier will
    retrieve from (course-scoped). Returns a compiled graph the ``discover_grounding`` tool invokes.
    """
    concepts_by_id = {kc.id: kc for kc in draft.concepts}
    concept_ids = [kc.id for kc in draft.concepts]

    async def plan_node(state: DiscoveryState) -> DiscoveryState:
        accepted = state.get("accepted", [])
        if state.get("round", 0) == 0:
            queries = build_discovery_queries(draft)
        else:
            # Re-query only the still-thin concepts (those short of cross-source coverage).
            uncovered = set(_uncovered(concept_ids, accepted))
            queries = [
                query for query in build_discovery_queries(draft) if query.kc_id in uncovered
            ]
        queries = queries[: budget.searches_per_round]
        await draft.agent.emit(
            AgentEventKind.TODO,
            todos=[{"content": f"Search: {query.text}", "status": "pending"} for query in queries],
        )
        await draft.agent.emit(
            AgentEventKind.REASONING,
            text=f"Planned {len(queries)} search(es) for this round's concepts.",
        )
        return {"queries": queries, "prev_total": len(accepted)}

    async def search_node(state: DiscoveryState) -> DiscoveryState:
        seen = set(state.get("seen_urls", []))
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
        return {"candidates": candidates[: budget.fetches_per_round], "seen_urls": sorted(seen)}

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
        round_accepted: list[CandidateSource] = []
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
            round_accepted.append(
                replace(source, trust_tier=scored.trust_tier, credibility=scored.credibility)
            )
            await _emit_evaluated(page, scored, accepted=True, reason=verdict.reason)
        return {"round_accepted": round_accepted}

    async def ingest_node(state: DiscoveryState) -> DiscoveryState:
        round_accepted = state.get("round_accepted", [])
        chunks = await ingestor.ingest(round_accepted, run_id=draft.run_id) if round_accepted else 0
        accepted = state.get("accepted", []) + round_accepted
        total_chunks = state.get("chunks_ingested", 0) + chunks
        covered = sorted({source.kc_id for source in accepted})
        await draft.agent.emit(
            AgentEventKind.REASONING,
            text=f"Ingested {chunks} grounding chunk(s); {len(covered)} concept(s) now grounded.",
        )
        return {"accepted": accepted, "chunks_ingested": total_chunks, "covered_kcs": covered}

    async def reflect_node(state: DiscoveryState) -> DiscoveryState:
        # Decide the loop's fate here (single source of truth for the routing), so the conditional
        # edge is a pure flag read. Continue only while concepts remain thin AND the round ceiling
        # is not hit AND the last round actually added evidence (else re-querying can't help).
        accepted = state.get("accepted", [])
        uncovered = _uncovered(concept_ids, accepted)
        round_index = state.get("round", 0) + 1
        made_progress = len(accepted) > state.get("prev_total", 0)
        should_continue = bool(uncovered) and round_index < budget.max_rounds and made_progress
        if should_continue:
            await draft.agent.emit(
                AgentEventKind.REASONING,
                text=f"{len(uncovered)} concept(s) still lack cross-source coverage — re-querying.",
            )
        elif uncovered:
            await draft.agent.emit(
                AgentEventKind.REASONING,
                text=f"Discovery done; {len(uncovered)} concept(s) left under-corroborated.",
            )
        return {"round": round_index, "should_continue": should_continue}

    def _route_after_reflect(state: DiscoveryState) -> str:
        return "plan" if state.get("should_continue") else END

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
    graph.add_node("reflect", reflect_node)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "fetch")
    graph.add_edge("fetch", "gate")
    graph.add_edge("gate", "ingest")
    graph.add_edge("ingest", "reflect")
    graph.add_conditional_edges("reflect", _route_after_reflect, {"plan": "plan", END: END})
    return graph.compile()
