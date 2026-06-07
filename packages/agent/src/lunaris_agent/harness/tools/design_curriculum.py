"""Curriculum design as a tool the agent calls (adapter over ``ICurriculumArchitect``).

The LLM-heavy backward-design work (grouping the graph's concepts into modules and writing
measurable objectives) stays in the existing architect subagent; the deterministic assembly
(item ids, difficulty-index, the non-decreasing-difficulty invariant) stays in
``CurriculumAssembler``. This tool wires them together, records the typed modules on the run
draft, and returns a compact summary for the agent to reason over before authoring.
"""

import structlog
from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import ProgressStage

from ...coverage import framework_coverage
from ...subagents.curriculum_architect import CurriculumAssembler, ICurriculumArchitect
from ..draft import CourseDraft

logger = structlog.get_logger()


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
