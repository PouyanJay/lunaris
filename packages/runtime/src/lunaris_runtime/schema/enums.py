from enum import StrEnum


class BloomLevel(StrEnum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class CourseStatus(StrEnum):
    DIAGNOSING = "diagnosing"
    MAPPING = "mapping"
    SEQUENCING = "sequencing"
    AUTHORING = "authoring"
    VERIFYING = "verifying"
    REVIEW = "review"
    PUBLISHED = "published"


class ProgressStage(StrEnum):
    """A boundary in the course-build pipeline, emitted as a ProgressEvent.

    Ordered as the orchestrator runs: the run starts, concepts are extracted, the
    prerequisite graph is built, the curriculum is designed, each module is authored
    (one event per module), claims are verified, and the run completes.
    """

    RUN_STARTED = "run_started"
    CONCEPTS_EXTRACTED = "concepts_extracted"
    GRAPH_BUILT = "graph_built"
    CURRICULUM_DESIGNED = "curriculum_designed"
    MODULE_AUTHORED = "module_authored"
    CLAIMS_VERIFIED = "claims_verified"
    RUN_COMPLETED = "run_completed"


class VerifierStatus(StrEnum):
    UNVERIFIED = "unverified"
    SUPPORTED = "supported"
    REVISE = "revise"
    CUT = "cut"


class RiskTier(StrEnum):
    HIGH = "high"
    LOW = "low"


class RiskCategory(StrEnum):
    MEDICAL = "medical"
    LEGAL = "legal"
    FINANCIAL = "financial"
    SAFETY = "safety"


class RiskOverride(StrEnum):
    AUTO = "auto"
    FORCE_HIGH = "force_high"
    FORCE_LOW = "force_low"


class Latency(StrEnum):
    AWAIT_FULL = "await_full"
    PROGRESSIVE = "progressive"


class Mode(StrEnum):
    ARTIFACT = "artifact"
    TUTOR = "tutor"


class QualityFloor(StrEnum):
    DRAFT = "draft"
    STANDARD = "standard"
    RIGOROUS = "rigorous"


class VisualKind(StrEnum):
    MERMAID = "mermaid"
    SVG = "svg"
    CHART = "chart"


class Pace(StrEnum):
    SLOW = "slow"
    NORMAL = "normal"
    FAST = "fast"
