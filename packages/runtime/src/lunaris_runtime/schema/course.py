from pydantic import Field

from .base import CourseModel
from .enums import CourseStatus, GoalType
from .instruction import Module
from .knowledge import Citation, PrerequisiteGraph
from .learner import LearnerModel
from .settings import BudgetLedger, CourseSettings, RiskProfile


class Course(CourseModel):
    """The single source of truth. Agents read slices they need, write the slice they own."""

    id: str
    topic: str  # the raw user query
    goal_concept: str = ""  # KnowledgeComponent id where the journey ends
    goal_type: GoalType = GoalType.KNOWLEDGE  # carried from the brief (CQ Phase 1.0)
    # An honest caveat when a research-needing goal could not be grounded in its real standard
    # (CQ Phase 1.6): empty when fully grounded or not research-needing; the reader shows it so a
    # generic course is never presented as an authoritative guide to the standard.
    scope_note: str = ""
    settings: CourseSettings = Field(default_factory=CourseSettings)
    risk: RiskProfile = Field(default_factory=RiskProfile)
    learner: LearnerModel = Field(default_factory=LearnerModel)
    graph: PrerequisiteGraph = Field(default_factory=PrerequisiteGraph)
    modules: list[Module] = Field(default_factory=list)
    provenance: list[Citation] = Field(default_factory=list)
    status: CourseStatus = CourseStatus.DIAGNOSING
    budget_ledger: BudgetLedger = Field(default_factory=BudgetLedger)
