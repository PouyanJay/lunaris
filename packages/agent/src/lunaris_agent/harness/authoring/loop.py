"""The author→verify→revise→triage reflection loop, as a deterministic LangGraph sub-graph.

This is the loop the MVP skipped. The agent delegates authoring to it; inside, control flow is
exact (a real ``StateGraph`` cycle), and the correctness guarantee stays in code:

  author → verify (the Failure-B moat) → decide → revise → verify → … → triage

The model authors and revises *prose*; whether a claim is supported is decided by the deterministic
``Verifier``, never the model. The loop is **adaptive**: it re-authors only modules with cut claims,
is bounded by a risk-tiered round cap (low stakes earn fewer revisions), and stops early the moment
a round stops shrinking the cut-claim set (no point spending budget the author can't use). Whatever
remains cut is **triaged**: dropped from publication (the publish gate already guarantees no cut
claim ships), and if a *goal-critical* claim is still unsupported the course is flagged for review
rather than published. (Softening a residual claim into a hedged, attributed form is a future
refinement — it needs the schema to model non-asserted claims.)
"""

from typing import Annotated, TypedDict

import structlog
from langchain_core.messages import AIMessage, AnyMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from lunaris_grounding import Verifier
from lunaris_runtime.schema import Module, ProgressStage, RiskTier, VerifierStatus

from ...lesson_claims import iter_claims
from ...subagents.module_author import LessonAssembler
from ..draft import CourseDraft
from .reviser_protocol import ILessonReviser

logger = structlog.get_logger()

# Revise-round budget by stakes; the hard ceiling caps even the high-risk tier.
_REVISE_CAP = {RiskTier.LOW: 1, RiskTier.HIGH: 3}
_HARD_CEILING = 3
_UNSET_CUT = 1_000_000  # sentinel "previous cut" so the first round never reads as no-progress


class AuthoringState(TypedDict, total=False):
    """The loop's working state. ``messages`` carries the narrative briefing/report (the sub-agent
    handover); the counters drive the bounded cycle. Counter keys are read with defaults so the
    sub-agent runtime can invoke the graph with only ``messages`` set."""

    messages: Annotated[list[AnyMessage], add_messages]
    round: int
    prev_cut: int
    cut: int


def _cut_texts_by_module(draft: CourseDraft) -> dict[str, list[str]]:
    """Map each module id to the texts of its still-cut claims (after a verify pass)."""
    cut_by_module: dict[str, list[str]] = {}
    for module in draft.modules:
        texts = [
            claim.text
            for lesson in module.lessons
            for claim in iter_claims([lesson])
            if claim.verifier_status is VerifierStatus.CUT
        ]
        if texts:
            cut_by_module[module.id] = texts
    return cut_by_module


def _is_goal_critical(module: Module, goal_concept: str | None) -> bool:
    return goal_concept is not None and goal_concept in module.kcs


def build_authoring_subgraph(
    reviser: ILessonReviser,
    verifier: Verifier,
    draft: CourseDraft,
    *,
    assembler: LessonAssembler | None = None,
) -> CompiledStateGraph:
    """Compile the author→verify→revise→triage loop over ``draft``'s modules.

    Closed over the run draft so the typed lessons + provenance it writes are exactly what
    ``finalize_course`` reads. Returns a compiled graph (state includes ``messages``) so it can be
    invoked directly or registered as a Deep Agents ``CompiledSubAgent``.
    """
    lesson_assembler = assembler or LessonAssembler()
    cap = min(_REVISE_CAP[draft.risk_tier], _HARD_CEILING)

    async def author(_state: AuthoringState) -> AuthoringState:
        for module in draft.modules:
            if module.lessons:
                continue  # already authored (e.g. a partial resume); only fill the gaps
            lesson_draft = await reviser.author(module)
            module.lessons = [lesson_assembler.assemble(lesson_draft, lesson_id=f"{module.id}-l0")]
            await draft.progress.emit(
                ProgressStage.MODULE_AUTHORED,
                f"Authored lesson: {module.title}",
                module_id=module.id,
            )
        # Seed the loop counters so the routing reads real values, not TypedDict defaults.
        return {"round": 0, "prev_cut": _UNSET_CUT}

    async def verify(state: AuthoringState) -> AuthoringState:
        lessons = [lesson for module in draft.modules for lesson in module.lessons]
        claims = list(iter_claims(lessons))
        citations = await verifier.verify(claims, risk_tier=draft.risk_tier)
        draft.provenance = citations
        cut = sum(len(texts) for texts in _cut_texts_by_module(draft).values())
        supported = len(claims) - cut
        logger.info(
            "authoring_loop_verified", run_id=draft.run_id, round=state.get("round", 0), cut=cut
        )
        await draft.progress.emit(
            ProgressStage.CLAIMS_VERIFIED,
            f"Verified {len(claims)} claims: {supported} supported, {cut} cut",
            claims_total=len(claims),
            claims_supported=supported,
            claims_cut=cut,
        )
        return {"cut": cut}

    async def revise(state: AuthoringState) -> AuthoringState:
        cut_by_module = _cut_texts_by_module(draft)
        for module in draft.modules:
            cut_texts = cut_by_module.get(module.id)
            if not cut_texts:
                continue
            revised = await reviser.revise(module, cut_texts)
            module.lessons = [lesson_assembler.assemble(revised, lesson_id=f"{module.id}-l0")]
        return {"prev_cut": state.get("cut", _UNSET_CUT), "round": state.get("round", 0) + 1}

    async def triage(state: AuthoringState) -> AuthoringState:
        cut_by_module = _cut_texts_by_module(draft)
        residual = sum(len(texts) for texts in cut_by_module.values())
        goal_critical = any(
            _is_goal_critical(module, draft.goal_concept)
            for module in draft.modules
            if module.id in cut_by_module
        )
        if goal_critical:
            draft.needs_review = True
        logger.info(
            "authoring_loop_finished",
            run_id=draft.run_id,
            rounds=state.get("round", 0),
            residual_cut=residual,
            needs_review=draft.needs_review,
        )
        rounds = state.get("round", 0)
        report = (
            f"Authored {len(draft.modules)} modules over {rounds} revision round(s); "
            f"{residual} claim(s) remained unsupported and were cut"
            + (" (goal-critical → flagged for review)." if goal_critical else ".")
        )
        return {"messages": [AIMessage(content=report)]}

    def _route_after_verify(state: AuthoringState) -> str:
        # Order matters: terminate on "all grounded", then on the budget cap, then on
        # no-progress — checking convergence before the cap would let a stalled-but-under-cap
        # loop keep spending revisions.
        cut = state.get("cut", 0)
        if cut == 0:
            return "triage"
        if state.get("round", 0) >= cap:
            return "triage"
        if cut >= state.get("prev_cut", _UNSET_CUT):
            return "triage"  # the last round did not shrink the cut set — stop spending budget
        return "revise"

    graph: StateGraph = StateGraph(AuthoringState)
    graph.add_node("author", author)
    graph.add_node("verify", verify)
    graph.add_node("revise", revise)
    graph.add_node("triage", triage)
    graph.add_edge(START, "author")
    graph.add_edge("author", "verify")
    graph.add_conditional_edges(
        "verify", _route_after_verify, {"revise": "revise", "triage": "triage"}
    )
    graph.add_edge("revise", "verify")
    graph.add_edge("triage", END)
    return graph.compile()
