from collections.abc import Iterable

from lunaris_runtime.schema import KnowledgeComponent

from lunaris_graph.verdict import PrereqVerdict


class StubPrereqJudge:
    """Deterministic judge configured with a known edge set.

    Returns a positive verdict iff ``(prerequisite.id, dependent.id)`` is in the
    configured set. Lets the deterministic assembly be tested without a model.
    """

    def __init__(self, edges: Iterable[tuple[str, str]], *, strength: float = 0.9) -> None:
        self._edges = set(edges)
        self._strength = strength

    async def judge(
        self, prerequisite: KnowledgeComponent, dependent: KnowledgeComponent
    ) -> PrereqVerdict:
        is_prereq = (prerequisite.id, dependent.id) in self._edges
        return PrereqVerdict(is_prereq=is_prereq, strength=self._strength if is_prereq else 0.0)
