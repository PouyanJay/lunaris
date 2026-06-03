from typing import Protocol

from lunaris_runtime.schema import CourseBrief

from .extraction import Extraction


class IConceptExtractor(Protocol):
    """Decomposes a topic into atomic knowledge components (KCs).

    Owns ``graph.nodes`` — the smallest teachable units, each with a definition,
    difficulty estimate, and Bloom ceiling. Swappable (live model vs. test stub).

    When ``brief`` is present and non-novice, extraction is ZPD-scoped to the gap (the competencies
    that distinguish the target level from the learner's assumed prior) rather than the full ladder;
    omitting both preserves the original novice behavior (the legacy/orchestrator path).
    """

    async def extract(
        self,
        topic: str,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> Extraction: ...
