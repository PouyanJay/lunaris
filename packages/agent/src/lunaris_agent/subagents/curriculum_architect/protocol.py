from typing import Protocol

from lunaris_runtime.schema import PrerequisiteGraph

from .plan import CurriculumPlan


class ICurriculumArchitect(Protocol):
    """Backward design: groups the graph's KCs into modules and writes a measurable,
    Bloom-verbed objective per KC (plus the items that will assess it) BEFORE any
    content exists. Owns ``modules[].objectives`` and module grouping.
    """

    async def design(self, graph: PrerequisiteGraph) -> CurriculumPlan: ...
