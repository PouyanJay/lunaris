"""The deterministic finalize step, exposed as the tool the agent calls when the build is done.

Parity + provenance are guaranteed by CODE here, not by the model: this reads the authoritative
typed results the other tools accumulated on the run ``draft`` and assembles the typed ``Course``,
runs the publish gate (the critic), and persists it. The model decides *when* to call this; it never
hand-types the structured course-object. (The agentic feel — streaming the assembly — is a UI
concern layered on top in P3; the backend stays deterministic.)
"""

import asyncio

import structlog
from langchain_core.tools import BaseTool, tool
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    Course,
    CourseStatus,
    GoalType,
    Module,
    PrerequisiteGraph,
    ProgressStage,
)

from ...coverage_critic import CoverageReport, ICoverageCritic
from ...critic import ICritic
from ...honesty import assess_grounding_honesty
from ...scope import estimate_scope
from ...subagents.scope_polisher import IScopePolisher
from ...subagents.visual_agent import VisualEngine
from ..draft import CourseDraft

logger = structlog.get_logger()


def _coverage_message(report: CoverageReport) -> str:
    """The COVERAGE_VERIFIED stage line — in the voice of the other stage lines (a count + verdict),
    so the build timeline reads consistently: clean, or how many promised competencies went unbuilt.
    """
    if report.is_clean:
        return "Coverage verified: every promised competency is built"
    count = len(report.gaps)
    noun = "competency" if count == 1 else "competencies"
    return f"Coverage gap: {count} promised {noun} not built — scoped out"


def _append_coverage_caveat(caveat: str, gaps: list[str]) -> str:
    """Fold any resource-coverage gaps (CQ Phase 2 T5) into the scope_note — no silent empty module.

    Appends an honest sentence naming the modules that ship without curated external resources, so
    the learner sees the gap rather than wondering why a module has no aids. Returns the caveat
    unchanged when there are no gaps.
    """
    if not gaps:
        return caveat
    note = f"Some modules ship without curated external resources: {', '.join(gaps)}."
    return f"{caveat} {note}".strip()


def _apply_quality_gates(course: Course, issues: list[str], draft: CourseDraft) -> None:
    """Set the course's scope_note + publish status from the critic, honesty, and coverage gates.

    Honesty gate (CQ Phase 1.6): an ungrounded research-needing goal carries an honest caveat and is
    withheld; a PARTIAL one still carries its caveat to the learner but may publish — so scope_note
    is set unconditionally (plus any resource gap, T5); only ``needs_review`` gates publication.
    The authoring loop's triage (``draft.needs_review``) withholds PUBLISHED even when the critic is
    clean. The course arrives in REVIEW; this promotes it to PUBLISHED only when every gate passes.
    """
    honesty = assess_grounding_honesty(draft.brief)
    course.scope_note = _append_coverage_caveat(honesty.caveat, draft.resource_coverage_gaps)
    # The scope-realism band (CQ Phase 3.1): an honest effort/timeline + does/doesn't framing,
    # computed from the brief's abstractions so the reader can set expectations up front.
    course.scope = estimate_scope(course, draft.brief)
    if not issues and not draft.needs_review and not honesty.needs_review:
        course.status = CourseStatus.PUBLISHED


def _modules_from_graph(graph: PrerequisiteGraph) -> list[Module]:
    """Trivial walking-skeleton assembly: one module per concept, in topological order.

    T2 replaces this with the curriculum + authored lessons accumulated on the draft; for the
    skeleton the modules carry only the concept they cover, proving the assemble→persist path.
    """
    by_id = {kc.id: kc for kc in graph.nodes}
    ordered = [by_id[kid] for kid in graph.topo_order if kid in by_id]
    return [
        Module(id=kc.id, title=kc.label, kcs=[kc.id], difficulty_index=kc.difficulty)
        for kc in ordered
    ]


def _assemble(draft: CourseDraft) -> Course:
    """Build the typed course-object from the draft's authoritative results.

    Enforces the finalize precondition in code: a course cannot be assembled before the
    prerequisite graph exists (the agent must call the graph tool first). This keeps a
    nullable working field (``draft.graph``) from silently becoming a malformed ``Course``.
    """
    if draft.graph is None:
        raise RuntimeError(
            f"course {draft.course_id!r}: finalize_course called before the prerequisite "
            "graph was built — call build_prerequisite_graph first"
        )
    # The graph is a hard precondition (a nullable working field that must not become a malformed
    # Course); the brief is not — direct-assembly paths (and several tests) build a course from a
    # graph alone, so a missing brief falls back to the schema's own goal_type default rather than
    # forcing every assembly site through interpret_request.
    goal_type = draft.brief.goal_type if draft.brief else GoalType.KNOWLEDGE
    return Course(
        id=draft.course_id,
        topic=draft.topic,
        goal_concept=draft.goal_concept or "",
        goal_type=goal_type,
        graph=draft.graph,
        modules=draft.modules or _modules_from_graph(draft.graph),
        provenance=draft.provenance,
    )


def make_finalize_course_tool(
    critic: ICritic,
    store: CourseStore,
    draft: CourseDraft,
    coverage_critic: ICoverageCritic,
    *,
    visual_engine: VisualEngine | None = None,
    scope_polisher: IScopePolisher | None = None,
) -> BaseTool:
    """Build the ``finalize_course`` tool, closed over the critics, the store, and the run draft.

    The ``coverage_critic`` (CQ Phase 4.2) is always present — like the structural ``critic``, never
    optional — because the gate always runs: the deterministic fail-safe stands in when the LLM
    judge can't (no key). It runs as the last gate, checks every promised competency is materially
    built, and folds any gap into the honest scope + a review flag (the COVERAGE_VERIFIED stage).

    When a ``visual_engine`` is wired, the assembled course is illustrated before the publish gate
    runs and before it is persisted — the agent-pipeline analogue of the Orchestrator's
    ``author → visual_engine → verify`` placement. Verification already ran inside the authoring
    subgraph (diagrams don't affect claim grounding), so this is the last enrichment before publish.
    Visuals are optional: without an engine the course finalizes exactly as before.
    """

    @tool
    async def finalize_course() -> dict[str, object]:
        """Assemble, gate, and persist the finished course from the work done so far.

        Call this once the concepts, prerequisite graph, curriculum, and lessons are ready.
        Returns ``{courseId, status, moduleCount, issues}``. ``status`` is ``published`` when the
        publish gate passes, else ``review`` with the blocking ``issues`` listed.
        """
        course = _assemble(draft)
        if visual_engine is not None:
            placed = await visual_engine.illustrate(course)
            logger.info("agent_course_illustrated", run_id=draft.run_id, visuals_placed=placed)
        course.status = CourseStatus.REVIEW
        issues = critic.review(course)
        _apply_quality_gates(course, issues, draft)
        # Coverage gate (CQ Phase 4.2): every promised competency must be materially built. A gap is
        # folded into the honest scope + flags review (T4); a clean report leaves the course as-is.
        # Runs after the scope band exists so it can extend it; before the wording polish so any
        # scoped-out competency reads in the same voice.
        report = await coverage_critic.review(course, brief=draft.brief)
        await draft.progress.emit(
            ProgressStage.COVERAGE_VERIFIED,
            _coverage_message(report),
            gap_count=len(report.gaps),
        )
        # Optional key-gated wording polish of the deterministic scope band (CQ Phase 3.1): refines
        # only the delivers/excludes copy, never the effort or the line counts (reconcile enforces
        # it). None (the no-key path) ships the deterministic band unchanged.
        if scope_polisher is not None and course.scope is not None:
            course.scope = await scope_polisher.polish(course.scope, brief=draft.brief)
        # CourseStore.save is synchronous file I/O; off-load it so the agent's event loop
        # is not blocked during the write (matters once the store is network-backed).
        await asyncio.to_thread(store.save, course)
        draft.course = course
        logger.info(
            "agent_course_finalized",
            run_id=draft.run_id,
            course_id=course.id,
            status=course.status.value,
            module_count=len(course.modules),
            issue_count=len(issues),
        )
        await draft.progress.emit(
            ProgressStage.RUN_COMPLETED,
            "Published" if course.status is CourseStatus.PUBLISHED else "Needs review",
            status=course.status,
        )
        return {
            "courseId": course.id,
            "status": course.status.value,
            "moduleCount": len(course.modules),
            "issues": issues,
        }

    return finalize_course
