from typing import Protocol

from lunaris_runtime.schema import KnowledgeComponent

from lunaris_graph.verdict import PrereqVerdict


class IPrereqJudge(Protocol):
    """Judges whether one knowledge component is a direct prerequisite of another.

    This is the only place the builder consults an LLM. Implementations are
    swappable (a live model, or a deterministic stub for tests).
    """

    async def judge(
        self, prerequisite: KnowledgeComponent, dependent: KnowledgeComponent
    ) -> PrereqVerdict: ...
