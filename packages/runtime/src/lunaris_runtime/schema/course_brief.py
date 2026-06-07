from typing import Self

from pydantic import Field, model_validator

from .base import CourseModel
from .enums import DetailDepth, GapMagnitude, GoalType, LanguageStyle, Level, StandardKind
from .standard_research import StandardResearch


class TargetStandard(CourseModel):
    """An externally-defined standard, certification, or exam the goal targets (e.g. "CLB 10").

    ``authority_hint`` records where its real definition lives (e.g. ``ircc.canada.ca``) so a
    later research step (P7.2) can ground competencies against the authoritative source.
    """

    name: str
    kind: StandardKind = StandardKind.EXTERNAL_STANDARD
    authority_hint: str = ""


class DeliverableShape(CourseModel):
    """Explicit shape constraints lifted verbatim from the request (e.g. "6 lessons")."""

    lessons: int | None = None


class Preferences(CourseModel):
    """How the learner wants the course pitched — captured at interpret time, steers authoring."""

    detail_depth: DetailDepth = DetailDepth.BALANCED
    language_style: LanguageStyle = LanguageStyle.BALANCED


class Gap(CourseModel):
    """The distance a course must close: from the learner's entry level to the goal (CQ Phase 1.0).

    ``entry_level`` is where the learner starts, ``target_level`` mirrors the brief's authoritative
    ``target_level`` (kept in sync by ``CourseBrief``), and ``magnitude`` sizes the leap. The
    research-depth policy (CQ Phase 1.2) scales a build's search/fetch budget off the gap, so a
    from-scratch credential climb earns more grounding than a same-level refinement.
    """

    entry_level: Level = Level.NOT_APPLICABLE
    target_level: Level = Level.NOT_APPLICABLE
    magnitude: GapMagnitude = GapMagnitude.MODERATE


class CourseBrief(CourseModel):
    """The interpreted request: a goal for a learner at a level, not a subject to enumerate.

    Produced by the goal interpreter as the first build stage and recorded on the run draft, so
    every later stage designs backward from the right desired result rather than enumerating a
    subject bottom-up. Frozen-at-generation config the way ``CourseSettings`` is — auditable and
    reproducible. The interpreter infers the brief honestly and flags ``needs_research`` without
    fabricating a named standard's content; the research stage (P7.2) then grounds it, recording the
    real competency descriptors + provenance on ``research`` via a copy.
    """

    subject: str
    goal: str
    # What kind of outcome the goal is (CQ Phase 1.0); shape + research depth branch on it.
    goal_type: GoalType = GoalType.KNOWLEDGE
    target_standard: TargetStandard | None = None
    target_level: Level = Level.NOT_APPLICABLE
    # Entry → target distance the course must close (CQ Phase 1.0); sizes research depth. The
    # gap's target_level is kept in sync with target_level below — the brief's field is canonical.
    gap: Gap = Field(default_factory=Gap)
    assumed_prior: str = ""
    audience: str = ""
    deliverable_shape: DeliverableShape = Field(default_factory=DeliverableShape)
    needs_research: bool = False
    domain_field: str = ""
    preferences: Preferences = Field(default_factory=Preferences)
    # Grounded by the research stage (P7.2): None until researched, or on a path that skips it.
    research: StandardResearch | None = None

    @model_validator(mode="after")
    def _sync_gap_target_level(self) -> Self:
        """Keep ``gap.target_level`` equal to the authoritative ``target_level`` (no drift).

        The interpreter infers the gap's entry level + magnitude; its target is not an independent
        input but a view of the brief's ``target_level``, so a model that omits or disagrees on it
        can't desync the two.
        """
        if self.gap.target_level is not self.target_level:
            self.gap = self.gap.model_copy(update={"target_level": self.target_level})
        return self
