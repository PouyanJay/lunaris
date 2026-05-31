"""Curriculum design as a tool the agent calls (adapter over ``ICurriculumArchitect``).

The LLM-heavy backward-design work (grouping the graph's concepts into modules and writing
measurable objectives) stays in the existing architect subagent; the deterministic assembly
(item ids, difficulty-index, the non-decreasing-difficulty invariant) stays in
``CurriculumAssembler``. This tool wires them together, records the typed modules on the run
draft, and returns a compact summary for the agent to reason over before authoring.
"""

from langchain_core.tools import BaseTool, tool
from lunaris_runtime.schema import ProgressStage

from ...subagents.curriculum_architect import CurriculumAssembler, ICurriculumArchitect
from ..draft import CourseDraft


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
        plan = await architect.design(draft.graph)
        modules = curriculum_assembler.assemble(plan, draft.graph)
        draft.modules = modules
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
