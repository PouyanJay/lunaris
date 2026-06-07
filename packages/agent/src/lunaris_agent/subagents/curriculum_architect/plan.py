# The four plan-layer dataclasses are tightly-coupled siblings (item → objective → module →
# curriculum) and are exported together as a deliberate exception to PYTHON.md's
# one-public-export-per-file rule.
from dataclasses import dataclass, field

from lunaris_runtime.schema import BloomLevel


@dataclass(frozen=True)
class AssessmentItemPlan:
    """One assessment item: the summative-check prompt + its gradeable pass criterion (CQ P4.1).

    ``pass_criterion`` is the explicit, concrete bar a passing response must clear ("Names >=2 AZs
    and a failover path"), written before the lesson so authoring works backward from it. Empty on
    the legacy / pre-P4 path (a bare prompt with no criterion).
    """

    prompt: str
    pass_criterion: str = ""


@dataclass(frozen=True)
class ObjectivePlan:
    """One measurable objective for a KC, with the assessment items that will prove it."""

    kc: str
    statement: str  # "Given X, the learner can Y"
    bloom_level: BloomLevel
    items: list[AssessmentItemPlan] = field(default_factory=list)


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
