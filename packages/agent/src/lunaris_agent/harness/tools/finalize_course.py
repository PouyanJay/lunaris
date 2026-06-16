"""The deterministic finalize step, exposed as the tool the agent calls when the build is done.

Parity + provenance are guaranteed by CODE here, not by the model: this reads the authoritative
typed results the other tools accumulated on the run ``draft`` and assembles the typed ``Course``,
runs the publish gate (the critic), and persists it. The model decides *when* to call this; it never
hand-types the structured course-object. (The agentic feel — streaming the assembly — is a UI
concern layered on top in P3; the backend stays deterministic.)
"""

import asyncio
from typing import NamedTuple

import structlog
from langchain_core.tools import BaseTool, tool
from lunaris_runtime.capabilities import capture_build_capabilities
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.schema import (
    AgentEventKind,
    CapabilityBuildTag,
    CapabilityMode,
    Course,
    CourseStatus,
    CourseVideos,
    GoalType,
    Module,
    PrerequisiteGraph,
    ProgressStage,
    VideoJobStatus,
    VideoKind,
)
from lunaris_runtime.video_build import lesson_content_fingerprint

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


# How many uncovered competencies to name before the phrase rolls up to "and N more" — enough to be
# specific, capped so the scope line stays scannable.
_MAX_UNCOVERED_NAMES_LISTED = 4


def _uncovered_names(report: CoverageReport, limit: int = _MAX_UNCOVERED_NAMES_LISTED) -> str:
    """The unbuilt competencies as one honest, bounded phrase (caps a long list so it stays
    scannable).
    """
    names = [gap.competency for gap in report.gaps]
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f", and {len(names) - limit} more"


def _scope_out_uncovered_competencies(course: Course, report: CoverageReport) -> None:
    """Fold the coverage gaps into the honest scope (CQ Phase 4.2, owner Q3): a scope_note sentence
    + an excludes line naming the promised competencies the course does not fully build, so a gap
    becomes an honest scope cut the reader sees rather than a silent omission. No-op when clean.

    ``scope_note`` is the pinned honesty guarantee — it always carries the verbatim names. The
    excludes line is reader copy the key-gated scope polisher may later reword (it preserves the
    line count, not its wording), so the named disclosure lives in scope_note regardless.
    """
    if report.is_clean:
        return
    listed = _uncovered_names(report)
    note = f"It does not fully build some promised competencies: {listed}."
    course.scope_note = f"{course.scope_note} {note}".strip()
    if course.scope is not None:
        line = f"Does not fully build: {listed}."
        course.scope = course.scope.model_copy(update={"excludes": [*course.scope.excludes, line]})


def _apply_quality_gates(
    course: Course, issues: list[str], draft: CourseDraft, coverage_report: CoverageReport
) -> None:
    """Set the course's scope_note + publish status from the critic, honesty, and coverage gates.

    Honesty gate (CQ Phase 1.6): an ungrounded research-needing goal carries an honest caveat and is
    withheld; a PARTIAL one still carries its caveat to the learner but may publish — so scope_note
    is set unconditionally (plus any resource gap, T5); only ``needs_review`` gates publication.
    The authoring loop's triage (``draft.needs_review``) withholds PUBLISHED even when the critic is
    clean. Coverage gate (CQ Phase 4.2): any promised competency the course does not build is folded
    into the honest scope AND withholds publication. The course arrives in REVIEW; this promotes it
    to PUBLISHED only when every gate passes.
    """
    honesty = assess_grounding_honesty(draft.brief)
    course.scope_note = _append_coverage_caveat(honesty.caveat, draft.resource_coverage_gaps)
    # The scope-realism band (CQ Phase 3.1): an honest effort/timeline + does/doesn't framing,
    # computed from the brief's abstractions so the reader can set expectations up front.
    course.scope = estimate_scope(course, draft.brief)
    _scope_out_uncovered_competencies(course, coverage_report)
    if (
        not issues
        and not draft.needs_review
        and not honesty.needs_review
        and coverage_report.is_clean
    ):
        course.status = CourseStatus.PUBLISHED


class _VideoOutcome(NamedTuple):
    """One lesson's video result, in the voice the canvas reads: the module's title (the lesson's
    subject — a lesson carries no title) and whether its video is ready."""

    module_title: str
    is_ready: bool


def _videos_label(total: int, ready: int, degraded: int) -> str:
    # Mirrors the voice of the other stage summaries ("21 concepts", "Coverage verified").
    noun = "video" if total == 1 else "videos"
    if degraded == 0:
        return f"{total} lesson {noun} ready"
    verb = "needs" if degraded == 1 else "need"
    return f"{total} lesson {noun} · {ready} ready · {degraded} {verb} a retry"


def _video_beat(outcome: _VideoOutcome) -> str:
    # The degraded line deliberately offers a learner-facing retry call-to-action.
    if outcome.is_ready:
        return f"Explainer video for “{outcome.module_title}” is ready."
    return (
        f"Explainer video for “{outcome.module_title}” could not be generated — "
        "retry it from the lesson."
    )


async def _enqueue_lesson_videos(course: Course, draft: CourseDraft) -> None:
    """Enqueue a lesson-video job per lesson, AFTER the course is persisted (the cloud-worker fix).

    The cloud video worker (V7) renders a lesson video by loading the course from the store
    (``course_store_lesson_provider``), so the course must already be saved or the worker fails the
    job "course not found". Enqueuing here — not during authoring, where it used to overlap the
    build — guarantees the worker can always load the course. Course-level videos snapshot their own
    grounding at curriculum design and never load the course, so they still enqueue early. A no-op
    when video is off (no coordinator), so the video-off path is unchanged; dedup on
    ``enqueued_video_jobs`` keeps it idempotent.
    """
    coordinator = draft.video_coordinator
    if coordinator is None:
        return
    for module in course.modules:
        for lesson in module.lessons:
            if lesson.id in draft.enqueued_video_jobs:
                continue
            job_id = await coordinator.enqueue_lesson(
                course_id=course.id,
                lesson_id=lesson.id,
                content_hash=lesson_content_fingerprint(lesson),
            )
            if job_id is not None:
                draft.enqueued_video_jobs[lesson.id] = job_id
            else:
                # The coordinator declined the job (gating / quota). Enqueuing is now the single
                # moment a lesson gets a video, so leave a breadcrumb — otherwise the lesson ships
                # video-less with no signal as to why.
                logger.debug(
                    "lesson_video_enqueue_skipped", run_id=draft.run_id, lesson_id=lesson.id
                )


async def _stitch_lesson_videos(course: Course, draft: CourseDraft) -> None:
    """Await the build's enqueued lesson videos and fold each into its lesson (V4-T1).

    Blocking-but-overlapped (plan §0): the jobs were enqueued the moment their modules cleared, so
    they have been rendering through the whole finalize tail; here the build blocks just long enough
    to collect them, degrading on failure (a failed video → a FAILED retry-state artifact on the
    lesson, never a blocked publish). A no-op when video is off (no coordinator) or nothing was
    enqueued, so the offline / video-off path finalizes byte-for-byte as before.
    """
    coordinator = draft.video_coordinator
    if coordinator is None or not draft.enqueued_video_jobs:
        return
    try:
        artifacts = await coordinator.collect(draft.enqueued_video_jobs)
    except Exception:
        # The coordinator already degrades per-job; this is the outer belt — a video must NEVER
        # abort the publish (plan §0). A wholesale collect failure ships the course video-less.
        logger.warning("agent_course_videos_collect_failed", run_id=draft.run_id, exc_info=True)
        return
    outcomes: list[_VideoOutcome] = []  # drives the canvas Videos-phase beats
    for module in course.modules:
        for lesson in module.lessons:
            artifact = artifacts.get(lesson.id)
            if artifact is None:
                continue
            lesson.video = artifact
            outcomes.append(_VideoOutcome(module.title, artifact.status is VideoJobStatus.READY))
    if not outcomes:
        return
    ready = sum(1 for outcome in outcomes if outcome.is_ready)
    degraded = len(outcomes) - ready
    logger.info(
        "agent_course_videos_stitched",
        run_id=draft.run_id,
        course_id=course.id,
        ready=ready,
        degraded=degraded,
    )
    # The canvas Videos phase (V4-T2): a coarse stage with the tally (degraded > 0 → amber on the
    # web), then one per-lesson beat so each video's outcome reads as its own line under the phase.
    await draft.progress.emit(
        ProgressStage.LESSON_VIDEOS,
        _videos_label(len(outcomes), ready, degraded),
        videos_total=len(outcomes),
        videos_degraded=degraded,
    )
    for outcome in outcomes:
        await draft.agent.emit(AgentEventKind.REASONING, text=_video_beat(outcome))


async def _stitch_course_videos(course: Course, draft: CourseDraft) -> None:
    """Await the build's course-level videos and fold them into ``Course.videos`` (V5-T2).

    The SUMMARY trailer + OVERVIEW intro, enqueued the moment the curriculum was designed, have been
    rendering through the build's tail; finalize blocks just long enough to collect them, degrading
    on failure (a failed course video → a FAILED retry-state artifact in the Overview section, never
    a blocked publish — plan §0). A no-op when video is off (no coordinator) or nothing enqueued,
    so the offline / video-off path finalizes byte-for-byte as before. The reader's Overview section
    resolves each artifact's signed URL via its ``provenance.job_id`` (V5-T3).
    """
    coordinator = draft.video_coordinator
    if coordinator is None or not draft.enqueued_course_videos:
        return
    try:
        artifacts = await coordinator.collect_course_videos(draft.enqueued_course_videos)
    except Exception:
        # The outer belt (the coordinator already degrades per-job): a course-level video must NEVER
        # abort the publish. A wholesale collect failure ships the course with no Overview section.
        logger.warning(
            "agent_course_level_videos_collect_failed", run_id=draft.run_id, exc_info=True
        )
        return
    course.videos = CourseVideos(
        summary=artifacts.get(VideoKind.SUMMARY),
        overview=artifacts.get(VideoKind.OVERVIEW),
    )
    logger.info(
        "agent_course_level_videos_stitched",
        run_id=draft.run_id,
        course_id=course.id,
        summary_status=course.videos.summary.status.value if course.videos.summary else None,
        overview_status=course.videos.overview.status.value if course.videos.overview else None,
    )


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


def _assemble(draft: CourseDraft, build_capabilities: list[CapabilityBuildTag]) -> Course:
    """Build the typed course-object from the draft's authoritative results.

    Enforces the finalize precondition in code: a course cannot be assembled before the
    prerequisite graph exists (the agent must call the graph tool first). This keeps a
    nullable working field (``draft.graph``) from silently becoming a malformed ``Course``.

    ``build_capabilities`` is captured by the caller inside the run's credential scope and set at
    construction (keyless-fallbacks T5), so the provider provenance is part of the assembled course
    rather than a post-construction mutation.
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
        build_capabilities=build_capabilities,
    )


def make_finalize_course_tool(
    critic: ICritic,
    store: ICourseStore,
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
        Returns ``{courseId, status, moduleCount, issues}``; ``status`` is ``published`` when the
        publish gate passes, else ``review`` with the blocking ``issues``. If the build isn't ready
        yet (no prerequisite graph), it returns ``{status: "incomplete", error}`` instead of
        finishing — do the missing steps, then call this again.
        """
        if draft.graph is None:
            # A weak planner (notably the keyless local model) can call finalize before doing the
            # work, which would crash the whole run. Return a corrective result instead, so the
            # agent builds the missing pieces and finalizes again. (``_assemble`` still raises when
            # called directly — this guard is on the tool boundary, not inside ``_assemble``.)
            logger.warning(
                "finalize_course_premature", run_id=draft.run_id, missing="prerequisite_graph"
            )
            return {
                "courseId": None,
                "status": "incomplete",
                "moduleCount": None,
                "issues": [],
                "error": (
                    "Cannot finalize yet — the prerequisite graph has not been built. Build the "
                    "course first: extract the concepts, call build_prerequisite_graph, design the "
                    "curriculum, and author the lessons; then call finalize_course again."
                ),
            }
        # Capture the build tag here (keyless-fallbacks T5): finalize runs inside the build's
        # credential scope, so it reflects which provider each capability actually used.
        course = _assemble(draft, capture_build_capabilities())
        if visual_engine is not None:
            placed = await visual_engine.illustrate(course)
            logger.info("agent_course_illustrated", run_id=draft.run_id, visuals_placed=placed)
        course.status = CourseStatus.REVIEW
        issues = critic.review(course)
        # Coverage gate (CQ Phase 4.2): every promised competency must be materially built. The
        # report is gathered before the quality gates so a gap can both extend the scope band and
        # withhold publication; the stage is emitted after, once the band reflects it.
        report = await coverage_critic.review(course, brief=draft.brief)
        _apply_quality_gates(course, issues, draft, report)
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
        # Persist the authored course BEFORE enqueuing its lesson videos. The cloud video worker
        # renders each lesson video by loading the course from the store, so the course must exist
        # there first — otherwise the worker fails every lesson video "course not found" (the V4
        # in-process worker shared memory and never hit this; the V7 cloud worker reads the DB).
        # The store's save is synchronous (file I/O for the file store, a blocking supabase-py call
        # for the Postgres store); off-load it so the agent's event loop isn't blocked on the write.
        await asyncio.to_thread(store.save, course)
        # Lesson videos enqueue here (against the now-persisted course); course-level videos were
        # enqueued at curriculum design (they snapshot their own grounding, so they need no
        # persisted course). Both then collect + fold in, degrade-on-failure so a video never blocks
        # the publish (plan §0).
        await _enqueue_lesson_videos(course, draft)
        await _stitch_lesson_videos(course, draft)
        await _stitch_course_videos(course, draft)
        # Re-persist with the stitched video refs (the save above predated them). Skipped when no
        # videos were ever enqueued, to spare the video-off build a redundant no-op write.
        if draft.enqueued_video_jobs or draft.enqueued_course_videos:
            await asyncio.to_thread(store.save, course)
        draft.course = course
        logger.info(
            "agent_course_finalized",
            run_id=draft.run_id,
            course_id=course.id,
            status=course.status.value,
            module_count=len(course.modules),
            issue_count=len(issues),
            # Which capabilities ran on a keyless fallback for this build (keyless-fallbacks T5):
            # capability names only (never a key), so a thin Draft course is diagnosable from logs.
            fallback_capabilities=[
                tag.capability.value
                for tag in course.build_capabilities
                if tag.mode is CapabilityMode.FALLBACK
            ],
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
            "error": None,
        }

    return finalize_course
