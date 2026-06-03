from typing import Protocol

from lunaris_runtime.schema import CourseBrief, PrerequisiteGraph

from .plan import CurriculumPlan


class ICurriculumArchitect(Protocol):
    """Backward design: groups the graph's KCs into modules and writes a measurable,
    Bloom-verbed objective per KC (plus the items that will assess it) BEFORE any
    content exists. Owns ``modules[].objectives`` and module grouping.

    When ``brief`` carries researched competencies (P7.2), the modules are mapped to them (backward
    design from the real standard); omitting it preserves the generic backward-design behavior.
    """

    async def design(
        self, graph: PrerequisiteGraph, *, brief: CourseBrief | None = None
    ) -> CurriculumPlan: ...
