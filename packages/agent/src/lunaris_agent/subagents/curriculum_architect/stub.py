from lunaris_runtime.schema import CourseBrief, PrerequisiteGraph

from .plan import CurriculumPlan


class StubCurriculumArchitect:
    """Returns a preconfigured plan. Lets the pipeline be tested without a model."""

    def __init__(self, plan: CurriculumPlan) -> None:
        self._plan = plan

    async def design(
        self, graph: PrerequisiteGraph, *, brief: CourseBrief | None = None
    ) -> CurriculumPlan:
        return self._plan
