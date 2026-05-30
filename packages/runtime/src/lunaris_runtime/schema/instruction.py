from pydantic import Field

from .base import CourseModel
from .enums import BloomLevel, VerifierStatus, VisualKind


class Objective(CourseModel):
    """Backward design: written before content. Must map to >=1 assessment item."""

    statement: str  # "Given X, the learner can Y"
    bloom_level: BloomLevel
    kc: str  # KnowledgeComponent id
    assessed_by: list[str] = Field(default_factory=list)  # Item ids


class Item(CourseModel):
    id: str
    prompt: str
    objective: str  # the Objective this item measures
    answer: str | None = None


class Assessment(CourseModel):
    items: list[Item] = Field(default_factory=list)


class Claim(CourseModel):
    """A factual sentence extracted for the verifier (build-spec §08)."""

    text: str
    supported_by: str | None = None  # Citation id; null => publish-blocked
    verifier_status: VerifierStatus = VerifierStatus.UNVERIFIED


class MayerFlags(CourseModel):
    coherence: bool = False
    signaling: bool = False
    spatial_contiguity: bool = False
    redundancy: bool = False


class Visual(CourseModel):
    kind: VisualKind
    source: str  # diagram-as-code
    rendered: str | None = None  # path to validated PNG/SVG
    mayer_checks: MayerFlags = Field(default_factory=MayerFlags)
    staged: list["Visual"] | None = None  # segmenting: progressive builds


class Segment(CourseModel):
    prose: str = ""
    visuals: list[Visual] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


class MerrillSegments(CourseModel):
    """All four phases are structurally required — a lesson can't exist without them."""

    activate: Segment
    demonstrate: Segment
    apply: Segment
    integrate: Segment


class GagneFlags(CourseModel):
    """Gagné's nine events — structurally present checklist."""

    gain_attention: bool = False
    state_objective: bool = False
    recall_prior: bool = False
    present_content: bool = False
    guide_learning: bool = False
    elicit_performance: bool = False
    provide_feedback: bool = False
    assess_performance: bool = False
    enhance_transfer: bool = False


class Lesson(CourseModel):
    id: str
    segments: MerrillSegments
    gagne: GagneFlags = Field(default_factory=GagneFlags)
    load_estimate: float = 0.0  # vs the cognitive-load budget


class Module(CourseModel):
    id: str
    title: str
    kcs: list[str] = Field(default_factory=list)
    objectives: list[Objective] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)
    assessment: Assessment = Field(default_factory=Assessment)
    difficulty_index: float = 0.0  # must be non-decreasing across modules
