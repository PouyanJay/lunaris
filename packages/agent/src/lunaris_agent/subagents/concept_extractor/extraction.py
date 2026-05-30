from dataclasses import dataclass

from lunaris_runtime.schema import KnowledgeComponent


@dataclass(frozen=True)
class Extraction:
    """The concept extractor's output: the KC set plus which KC is the goal."""

    kcs: list[KnowledgeComponent]
    goal_id: str
