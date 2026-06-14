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
from lunaris_grounding import Evidence, Verifier, render_evidence
from lunaris_runtime.schema import AgentEventKind, Module, ProgressStage, RiskTier, VerifierStatus

from ...lesson_claims import iter_claims
from ...subagents.module_author import LessonAssembler
from ..draft import CourseDraft
from .reviser_protocol import ILessonReviser

logger = structlog.get_logger()

# Revise-round budget by stakes; the hard ceiling caps even the high-risk tier.
_REVISE_CAP = {RiskTier.LOW: 1, RiskTier.HIGH: 3}
_HARD_CEILING = 3
_UNSET_CUT = 1_000_000  # sentinel "previous cut" so the first round never reads as no-progress
# Cap the grounding evidence put in front of the author so a many-KC module can't blow the prompt.
_MAX_GROUNDING_ITEMS = 12


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


async def _enqueue_cleared_module_videos(draft: CourseDraft, *, ready_module_ids: set[str]) -> None:
    """Enqueue a lesson-video job for each ready module whose video isn't already enqueued (V4-T0).

    "Ready" = the module's lessons are final and won't be revised again: a module with no cut claims
    after a verify pass (it won't re-enter ``revise``), or every module at ``triage`` (the loop is
    done). Enqueuing the moment a module clears — not when the whole loop ends — is what overlaps
    video rendering with the rest of the build (plan §0). No coordinator (video off) ⇒ a no-op, so
    the gate stays in the composition root. Dedup is the draft's ``enqueued_video_jobs`` keys, so a
    module enqueues exactly once even though ``verify`` runs each round.
    """
    coordinator = draft.video_coordinator
    if coordinator is None:
        return
    for module in draft.modules:
        if module.id not in ready_module_ids or not module.lessons:
            continue
        # One lesson per module today (the assembler stamps a single ``{module.id}-l0``).
        lesson_id = module.lessons[0].id
        if lesson_id in draft.enqueued_video_jobs:
            continue
        job_id = await coordinator.enqueue_lesson(course_id=draft.course_id, lesson_id=lesson_id)
        if job_id is not None:
            draft.enqueued_video_jobs[lesson_id] = job_id


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
    concepts_by_id = {kc.id: kc for kc in draft.concepts}

    async def _grounding_for(queries: list[str]) -> str:
        # Grounded authoring (CQ Phase 1.5): reuse the verifier's own retriever so the author writes
        # from the same corpus the gate will check — no separate retriever, no loosened threshold.
        # Best-effort: grounding is advisory, so a retrieval failure degrades to no grounding rather
        # than crashing the build (mirrors the verifier's per-claim degradation).
        evidence_by_id: dict[str, Evidence] = {}
        for query in queries:
            try:
                hits = await verifier.retriever.retrieve(query, course_id=draft.course_id)
            except Exception:
                logger.warning("grounding_retrieval_failed", run_id=draft.run_id, exc_info=True)
                continue
            for evidence in hits:
                evidence_by_id.setdefault(evidence.citation.id, evidence)
        if not evidence_by_id:
            return ""
        return render_evidence(list(evidence_by_id.values())[:_MAX_GROUNDING_ITEMS])

    def _module_queries(module: Module) -> list[str]:
        queries: list[str] = []
        for kc_id in module.kcs:
            concept = concepts_by_id.get(kc_id)
            queries.append(
                f"{concept.label}. {concept.definition}" if concept else f"{kc_id} {module.title}"
            )
        return queries or [module.title]

    async def author(_state: AuthoringState) -> AuthoringState:
        for module in draft.modules:
            if module.lessons:
                continue  # already authored (e.g. a partial resume); only fill the gaps
            # Retrieve the module's per-KC evidence before authoring (CQ Phase 1.5).
            grounding = await _grounding_for(_module_queries(module))
            # Thread the interpreted brief + the learner's frontier so the arc is personalized —
            # aimed at the module's competency, pitched at the level, scoped above the frontier.
            lesson_draft = await reviser.author(
                module, brief=draft.brief, frontier=draft.frontier, grounded_evidence=grounding
            )
            module.lessons = [lesson_assembler.assemble(lesson_draft, lesson_id=f"{module.id}-l0")]
            await draft.progress.emit(
                ProgressStage.MODULE_AUTHORED,
                f"Authored lesson: {module.title}",
                module_id=module.id,
            )
            # Surface each module as it lands (the tap can't see inside this subagent), so the
            # Lessons phase streams real progress instead of one opaque "running…" task call.
            await draft.agent.emit(
                AgentEventKind.REASONING, text=f"Authored the lesson for “{module.title}”."
            )
        # Seed the loop counters so the routing reads real values, not TypedDict defaults.
        return {"round": 0, "prev_cut": _UNSET_CUT}

    async def verify(state: AuthoringState) -> AuthoringState:
        lessons = [lesson for module in draft.modules for lesson in module.lessons]
        claims = list(iter_claims(lessons))
        # Course-scoped (P6.1): the build verifies claims against THIS course's grounding corpus
        # (its manually-vouched sources), never another topic's evidence.
        citations = await verifier.verify(
            claims, risk_tier=draft.risk_tier, course_id=draft.course_id
        )
        draft.provenance = citations
        cut_by_module = _cut_texts_by_module(draft)
        cut = sum(len(texts) for texts in cut_by_module.values())
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
        await draft.agent.emit(
            AgentEventKind.REASONING,
            text=(
                f"Verified {len(claims)} claims against the corpus — "
                f"{supported} supported, {cut} cut."
            ),
        )
        # A module with no cut claims this pass is final (it won't re-enter ``revise``) — enqueue
        # its lesson video now so it renders while the remaining modules still revise (the overlap).
        ready = {module.id for module in draft.modules if module.id not in cut_by_module}
        await _enqueue_cleared_module_videos(draft, ready_module_ids=ready)
        return {"cut": cut}

    async def revise(state: AuthoringState) -> AuthoringState:
        cut_by_module = _cut_texts_by_module(draft)
        await draft.agent.emit(
            AgentEventKind.REASONING,
            text=(
                f"Revising {len(cut_by_module)} module(s) with unsupported claims, "
                "then re-verifying."
            ),
        )
        for module in draft.modules:
            cut_texts = cut_by_module.get(module.id)
            if not cut_texts:
                continue
            # Claim-repair (CQ Phase 1.5): retrieve evidence for the cut claims so the reviser
            # rewrites them down to what the corpus states, not re-assert from memory.
            grounding = await _grounding_for(cut_texts)
            try:
                revised = await reviser.revise(
                    module,
                    cut_texts,
                    brief=draft.brief,
                    frontier=draft.frontier,
                    grounded_evidence=grounding,
                )
            except ValueError:
                # The reviser exhausted its bounded parse-repair turns (a small draft-tier model
                # may never emit a parseable four-phase lesson). Revision is an IMPROVEMENT pass
                # over an already-authored lesson — keep the existing lesson rather than fail the
                # whole run at its last step: the still-cut claims stay cut, the no-progress
                # route sends the loop to triage, and the publish gate guarantees no cut claim
                # ships. Mirrors the grounding/verifier per-claim degradation philosophy.
                logger.warning(
                    "lesson_revision_unparseable",
                    run_id=draft.run_id,
                    module=module.id,
                    exc_info=True,
                )
                await draft.agent.emit(
                    AgentEventKind.REASONING,
                    text=(
                        f"Could not produce a usable revision for “{module.title}” — "
                        "keeping the previous lesson; its unsupported claims will be cut."
                    ),
                )
                continue
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
        # The loop is done: every authored module is final (a residual-cut module still publishes
        # its supported claims), so enqueue any lesson video not enqueued during the verify rounds.
        await _enqueue_cleared_module_videos(
            draft, ready_module_ids={module.id for module in draft.modules}
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
