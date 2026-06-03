from dataclasses import dataclass, field

from lunaris_runtime.schema import BloomLevel


@dataclass(frozen=True)
class ObjectivePlan:
    """One measurable objective for a KC, with the prompts that will assess it."""

    kc: str
    statement: str  # "Given X, the learner can Y"
    bloom_level: BloomLevel
    item_prompts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModulePlan:
    """A group of KCs taught together, with their objectives. Lessons come later (Stage 4).

    ``competency`` is the researched target skill the module covers (P7.3) when the brief grounded
    the standard; ``None`` on the legacy / no-research path.
    """

    title: str
    kcs: list[str]
    objectives: list[ObjectivePlan]
    competency: str | None = None


@dataclass(frozen=True)
class CurriculumPlan:
    """The curriculum architect's output: ordered modules covering the graph."""

    modules: list[ModulePlan]
