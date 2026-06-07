from dataclasses import dataclass, field

from lunaris_runtime.schema import CompetencyArea


@dataclass(frozen=True)
class Distillation:
    """One round's parsed distillation (CQ Phase 1.1): the structured framework plus what to deepen.

    ``areas`` is the structured competency framework; ``competencies`` is its flattened view (or the
    flat fallback when the model returned no areas); ``follow_up_queries`` are the searches the
    model proposes for areas the sources covered thinly — the signal that drives the next round.
    """

    areas: list[CompetencyArea] = field(default_factory=list)
    competencies: list[str] = field(default_factory=list)
    score_table: list[str] = field(default_factory=list)
    follow_up_queries: list[str] = field(default_factory=list)
