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

    Ordered as the agent runs: the run starts, the request is interpreted into a brief,
    concepts are extracted, the prerequisite graph is built, the curriculum is designed,
    each module is authored (one event per module), claims are verified, and the run
    completes.
    """

    RUN_STARTED = "run_started"
    BRIEF_INTERPRETED = "brief_interpreted"
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
    SPEC = "spec"  # a typed VisualSpec drawn by the web; no diagram-as-code source


class Pace(StrEnum):
    SLOW = "slow"
    NORMAL = "normal"
    FAST = "fast"


class AgentEventKind(StrEnum):
    """The kind of a fine-grained agent-execution event in the live transcript feed."""

    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TODO = "todo"


class RunEventKind(StrEnum):
    """Which stream a persisted build event came from (build-timeline replay).

    The two live SSE channels — coarse ``progress`` stages and fine-grained ``agent`` transcript
    beats — are persisted into one ordered log; the kind tells the replay client which wire shape
    (``ProgressEvent`` vs ``AgentEvent``) the row's ``payload`` carries.
    """

    PROGRESS = "progress"
    AGENT = "agent"


class RunStatus(StrEnum):
    """The operational lifecycle of a course-build run (the sidebar history status).

    Distinct from ``CourseStatus`` (the pedagogical lifecycle of the course itself):
    a run is ``RUNNING`` while building, then ``COMPLETED``, ``FAILED``, or ``CANCELLED``
    (explicitly terminated mid-build — distinct from FAILED, which is an error/disconnect).
    """

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Level(StrEnum):
    """The learner level a course targets (the interpreted brief's ``target_level``).

    Drives gap-scoped design (P7): an ``ADVANCED`` goal prunes foundations a ``NOVICE`` course
    teaches. ``NOT_APPLICABLE`` covers goals with no meaningful proficiency ladder.
    """

    NOVICE = "novice"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    NOT_APPLICABLE = "n/a"


class StandardKind(StrEnum):
    """What kind of external target a goal's standard is (the brief's ``target_standard``)."""

    EXTERNAL_STANDARD = "external_standard"
    CERTIFICATION = "certification"
    EXAM = "exam"
    INFORMAL = "informal"


class DetailDepth(StrEnum):
    """How much depth the learner wants — a ``preferences`` input that steers authoring voice."""

    CONCISE = "concise"
    BALANCED = "balanced"
    IN_DEPTH = "in_depth"


class LanguageStyle(StrEnum):
    """The register the course is written in — a ``preferences`` input for authoring voice."""

    SIMPLE = "simple"
    BALANCED = "balanced"
    SOPHISTICATED = "sophisticated"
    SCIENTIFIC = "scientific"
