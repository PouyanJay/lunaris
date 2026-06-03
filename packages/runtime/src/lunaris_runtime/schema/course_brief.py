from pydantic import Field

from .base import CourseModel
from .enums import DetailDepth, LanguageStyle, Level, StandardKind
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
    target_standard: TargetStandard | None = None
    target_level: Level = Level.NOT_APPLICABLE
    assumed_prior: str = ""
    audience: str = ""
    deliverable_shape: DeliverableShape = Field(default_factory=DeliverableShape)
    needs_research: bool = False
    domain_field: str = ""
    preferences: Preferences = Field(default_factory=Preferences)
    # Grounded by the research stage (P7.2): None until researched, or on a path that skips it.
    research: StandardResearch | None = None
