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

    Ordered as the agent runs: the run starts, the request is interpreted into a brief, the target
    standard is researched (grounding the brief in real competencies), the learner is modeled (the
    frontier of what they already know), concepts are extracted, the prerequisite graph is built,
    the curriculum is designed, each module is authored (one event per module), claims are verified,
    and the run completes.
    """

    RUN_STARTED = "run_started"
    BRIEF_INTERPRETED = "brief_interpreted"
    STANDARD_RESEARCHED = "standard_researched"
    LEARNER_MODELED = "learner_modeled"
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


class ResearchStatus(StrEnum):
    """How well the research stage grounded the brief's target standard (P7.2).

    Research is always-on but bounded + best-effort: it degrades honestly rather than blocking a
    build. ``COMPLETE`` = competencies were distilled from fetched sources; ``PARTIAL`` = some
    sources were reached but the budget ran out or extraction was thin; ``UNAVAILABLE`` = no usable
    source (no search key, search returned nothing, or every fetch failed) — design falls back to
    the model's internal knowledge, surfaced as such in the UI.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class TrustTier(StrEnum):
    """A source's authority tier, classified deterministically from its domain (P7.2).

    A minimal, real trust model the research + (later) resource-curation stages share, and that P6
    extends with its richer registry/field packs. ``OFFICIAL`` = the standard's own authority or a
    government/standards body; ``REPUTABLE`` = an established institution (university, major org);
    ``OPEN`` = the general web; ``BLOCKED`` = a denylisted domain (never fetched or shown).
    """

    OFFICIAL = "official"
    REPUTABLE = "reputable"
    OPEN = "open"
    BLOCKED = "blocked"
