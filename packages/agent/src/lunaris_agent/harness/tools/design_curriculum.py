"""Curriculum design as a tool the agent calls (adapter over ``ICurriculumArchitect``).

The LLM-heavy backward-design work (grouping the graph's concepts into modules and writing
measurable objectives) stays in the existing architect subagent; the deterministic assembly
(item ids, difficulty-index, the non-decreasing-difficulty invariant) stays in
``CurriculumAssembler``. This tool wires them together, records the typed modules on the run
draft, and returns a compact summary for the agent to reason over before authoring.
"""

import structlog
from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import ProgressStage, VideoKind

from ...coverage import framework_coverage
from ...subagents.curriculum_architect import CurriculumAssembler, ICurriculumArchitect
from ..draft import CourseDraft

logger = structlog.get_logger()


async def _enqueue_course_videos(draft: CourseDraft) -> None:
    """Enqueue the SUMMARY trailer + OVERVIEW intro for the build (V5-T2), best-effort.

    Called once the curriculum is designed — both grounding inputs (the researched brief and the
    modules) are final here. ``video_coordinator is None`` (video off / keyless / unowned) makes it
    a no-op, so the gate lives in the composition root and the harness only checks presence. The
    coordinator dedups per build and swallows queue errors — a hiccup degrades to "no course video",
    not a broken build. The returned job ids ride on the draft for finalize to await.
    """
    coordinator = draft.video_coordinator
    if coordinator is None:
        return
    summary_job = await coordinator.enqueue_summary(
        course_id=draft.course_id, topic=draft.topic, modules=draft.modules
    )
    if summary_job is not None:
        draft.enqueued_course_videos[VideoKind.SUMMARY] = summary_job
    # The overview grounds in the brief + its researched standard; skip it on a briefless
    # (direct-assembly) build, which has nothing to ground the intro against.
    if draft.brief is not None:
        overview_job = await coordinator.enqueue_overview(
            course_id=draft.course_id, brief=draft.brief
        )
        if overview_job is not None:
            draft.enqueued_course_videos[VideoKind.OVERVIEW] = overview_job


def make_design_curriculum_tool(
    architect: ICurriculumArchitect,
    draft: CourseDraft,
    assembler: CurriculumAssembler | None = None,
) -> BaseTool:
    """Build the ``design_curriculum`` tool, closed over the architect, draft, and assembler.

    Requires the prerequisite graph to exist on the draft (the agent must build it first); the
    curriculum is grouped over that authoritative ordering, so module sequence respects the
    prerequisites.
    """
    curriculum_assembler = assembler or CurriculumAssembler()

    @tool
    async def design_curriculum() -> dict[str, object]:
        """Group the ordered concepts into modules with measurable objectives (backward design).

        Call this after ``build_prerequisite_graph``. Returns ``{moduleCount, modules: [{id, title,
        kcs, objectiveCount}]}``. Difficulty is non-decreasing across modules and every objective is
        backed by an assessment item — both guaranteed by the tool, not by you.
        """
        if draft.graph is None:
            raise RuntimeError(
                f"course {draft.course_id!r}: design_curriculum called before the prerequisite "
                "graph was built — call build_prerequisite_graph first"
            )
        # brief threads the researched competencies into the architect (backward design from the
        # real standard); None on the legacy/no-research path leaves the design generic.
        plan = await architect.design(draft.graph, brief=draft.brief)
        modules = curriculum_assembler.assemble(plan, draft.graph)
        draft.modules = modules
        # Structure-derives-from-research signal (CQ Phase 1.3): when the standard was researched,
        # surface how much of its framework the curriculum actually maps onto — drift (competencies
        # left uncovered) is observable in the logs rather than silent. The hard gate is Phase 4.
        research = draft.brief.research if draft.brief else None
        if research is not None and research.competencies:
            covered, uncovered = framework_coverage(research, modules)
            logger.info(
                "curriculum_competency_coverage",
                run_id=draft.run_id,
                covered=len(covered),
                uncovered=len(uncovered),
                # A few examples keep the INFO line bounded even if many competencies go uncovered.
                uncovered_sample=uncovered[:5],
            )
        await draft.progress.emit(
            ProgressStage.CURRICULUM_DESIGNED,
            f"Designed curriculum: {len(modules)} modules",
            module_count=len(modules),
        )
        # Enqueue the course-level videos now (V5-T2): this is the first point where BOTH the
        # researched brief (research_standard ran before curriculum) and the curriculum are final —
        # both the OVERVIEW (brief + standard) and SUMMARY (curriculum) ground correctly while their
        # ~3-min / ~75s renders overlap the long authoring phase still ahead. No coordinator (video
        # off / keyless / unowned) ⇒ a no-op, so the gate stays in the composition root.
        await _enqueue_course_videos(draft)
        return {
            "moduleCount": len(modules),
            "modules": [
                {
                    "id": module.id,
                    "title": module.title,
                    "kcs": list(module.kcs),
                    "objectiveCount": len(module.objectives),
                }
                for module in modules
            ],
        }

    return design_curriculum
