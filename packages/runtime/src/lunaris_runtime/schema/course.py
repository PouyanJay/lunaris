from pydantic import Field

from .base import CourseModel
from .build_provenance import CapabilityBuildTag
from .course_scope import CourseScope
from .course_videos import CourseVideos
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
    # The scope-realism band (CQ Phase 3.1): effort/timeline + what this does / does not get you,
    # computed at finalize from the brief. None on a pre-Phase-3 / direct-assembly course = no band.
    scope: CourseScope | None = None
    settings: CourseSettings = Field(default_factory=CourseSettings)
    risk: RiskProfile = Field(default_factory=RiskProfile)
    learner: LearnerModel = Field(default_factory=LearnerModel)
    graph: PrerequisiteGraph = Field(default_factory=PrerequisiteGraph)
    modules: list[Module] = Field(default_factory=list)
    provenance: list[Citation] = Field(default_factory=list)
    # Which provider produced each key-gated capability's contribution (keyless-fallbacks T5):
    # captured at finalize from the run's credential scope and persisted, so a Draft course carries
    # an honest record of the fallback that built it. Empty on pre-T5 / direct-assembly courses.
    build_capabilities: list[CapabilityBuildTag] = Field(default_factory=list)
    status: CourseStatus = CourseStatus.DIAGNOSING
    budget_ledger: BudgetLedger = Field(default_factory=BudgetLedger)
    # The course's opening videos — the V5 Overview section (a SUMMARY trailer + an OVERVIEW intro).
    # None until the build's finalize stitches them (V5-T2); a course built before V5, with video
    # off, or whose course render degraded carries none — the reader shows no Overview section.
    videos: CourseVideos | None = None
