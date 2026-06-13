from pydantic import Field

from .base import CourseModel
from .enums import BloomLevel, VerifierStatus, VisualKind
from .resource import Resource
from .video_artifact import VideoArtifact
from .visual_spec import VisualSpec


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
    # Backward design (CQ Phase 4.1): the explicit, concrete, gradeable bar this item is judged
    # against — what a passing response must show ("Names >=2 AZs and a failover path"), not the
    # unscored "does your register align?". Written before the lesson so authoring works backward
    # from it. Scaffolding the learner reads, NOT a factual claim — the verifier never grounds it.
    # Empty on the legacy / pre-P4 path (the reader simply shows no check line).
    pass_criterion: str = ""


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
    source: str  # diagram-as-code (Mermaid) — the renderer's fallback
    rendered: str | None = None  # path to validated PNG/SVG
    spec: VisualSpec | None = None  # typed branded-renderer spec; None => render from source
    mayer_checks: MayerFlags = Field(default_factory=MayerFlags)
    staged: list["Visual"] | None = None  # segmenting: progressive builds


class Segment(CourseModel):
    prose: str = ""
    visuals: list[Visual] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    # Curated external aids attached to this phase (P7.4) — suggested, not part of the verified
    # lesson, so they carry no claims and the verifier never grounds them. Default empty; a course
    # built before P7.4 (or a phase no resource suited) simply has none.
    resources: list[Resource] = Field(default_factory=list)


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
    # The lesson arc's bookends (P7.3): the entry expectations the lesson assumes ("what this lesson
    # expects you already know") and the self-checks a learner runs to confirm they reached the
    # competency. Scaffolding the learner reads — NOT factual claims, so the verifier never grounds
    # them. Personalized per course at authoring time (from the learner's frontier, the module's
    # competency, and the requested detail/register), so the arc mirrors the standard rather than a
    # generic Merrill climb.
    expects: list[str] = Field(default_factory=list)
    self_check: list[str] = Field(default_factory=list)
    gagne: GagneFlags = Field(default_factory=GagneFlags)
    load_estimate: float = 0.0  # vs the cognitive-load budget
    # None until the build populates it; defined now so the course payload shape is stable and a
    # lesson's video provenance has a home without a later migration.
    video: VideoArtifact | None = None


class Module(CourseModel):
    id: str
    title: str
    kcs: list[str] = Field(default_factory=list)
    # The researched target competency this module covers (P7.3): backward design from the real
    # standard tags each module with the one skill it builds, so the reader can show what it earns
    # and the architect designs toward it. None on the legacy / no-research path.
    competency: str | None = None
    objectives: list[Objective] = Field(default_factory=list)
    lessons: list[Lesson] = Field(default_factory=list)
    assessment: Assessment = Field(default_factory=Assessment)
    difficulty_index: float = 0.0  # must be non-decreasing across modules
