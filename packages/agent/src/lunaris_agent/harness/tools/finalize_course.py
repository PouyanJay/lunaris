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

from ...critic import ICritic
from ...honesty import assess_grounding_honesty
from ...subagents.visual_agent import VisualEngine
from ..draft import CourseDraft

logger = structlog.get_logger()


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
    *,
    visual_engine: VisualEngine | None = None,
) -> BaseTool:
    """Build the ``finalize_course`` tool, closed over the critic, the store, and the run draft.

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
        # Honesty gate (CQ Phase 1.6): an ungrounded research-needing goal carries an honest caveat
        # and is withheld; a PARTIAL one still carries its caveat to the learner but may publish —
        # so scope_note is set unconditionally, only needs_review gates publication.
        honesty = assess_grounding_honesty(draft.brief)
        course.scope_note = honesty.caveat
        # The authoring loop's triage flags a course whose goal-critical claim could not be
        # grounded within budget; withhold PUBLISHED even when the structural critic is clean.
        if not issues and not draft.needs_review and not honesty.needs_review:
            course.status = CourseStatus.PUBLISHED
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
