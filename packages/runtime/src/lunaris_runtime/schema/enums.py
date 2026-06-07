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
    the curriculum is designed, the grounding corpus is prepared (P6 — the evidence each claim is
    verified against: first SEEDED from the sources the research stage already fetched, then
    DISCOVERED fresh to fill the gaps), each module is authored (one event per module), claims are
    verified, learning resources are curated per lesson, coverage is verified (CQ Phase 4 — every
    researched competency is materially built, or honestly scoped out), and the run completes.
    """

    RUN_STARTED = "run_started"
    BRIEF_INTERPRETED = "brief_interpreted"
    STANDARD_RESEARCHED = "standard_researched"
    LEARNER_MODELED = "learner_modeled"
    CONCEPTS_EXTRACTED = "concepts_extracted"
    GRAPH_BUILT = "graph_built"
    CURRICULUM_DESIGNED = "curriculum_designed"
    GROUNDING_SEEDED = "grounding_seeded"
    GROUNDING_DISCOVERED = "grounding_discovered"
    MODULE_AUTHORED = "module_authored"
    CLAIMS_VERIFIED = "claims_verified"
    RESOURCES_CURATED = "resources_curated"
    COVERAGE_VERIFIED = "coverage_verified"
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
    SOURCE_EVALUATED = "source_evaluated"


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


class GoalType(StrEnum):
    """What kind of outcome a course's goal is (course-level, on the brief) — CQ Phase 1.0.

    The classification the deliverable shape and research depth branch on, keyed off the goal's
    nature rather than its topic (the Genericity Rule): ``KNOWLEDGE`` = understand a body of
    material (the document is the course); ``SKILL`` = become able to *do* something (a practised
    capability); ``CREDENTIAL`` = pass an externally-defined exam/certification (an exam maps here,
    not to a modality); ``BEHAVIOR`` = change an ongoing habit or practice over time. Defaults to
    ``KNOWLEDGE`` — the shape today's content-dense document already serves.
    """

    KNOWLEDGE = "knowledge"
    SKILL = "skill"
    CREDENTIAL = "credential"
    BEHAVIOR = "behavior"


class GapMagnitude(StrEnum):
    """How large the leap from the learner's entry level to the goal is (CQ Phase 1.0).

    Part of the brief's ``gap`` (entry → target). Inferred from the goal's nature, not its topic:
    ``SMALL`` = a refinement at roughly the same level; ``MODERATE`` = one band of growth;
    ``LARGE`` = several bands or a from-scratch climb. The research-depth policy (CQ Phase 1.2)
    earns more searches/fetches/iterations for a larger gap. Defaults to ``MODERATE``.
    """

    SMALL = "small"
    MODERATE = "moderate"
    LARGE = "large"


class Modality(StrEnum):
    """How a single knowledge component is learned (per-KC, CQ Phase 1.0).

    Orthogonal to the course-level ``GoalType``: one course mixes modalities (CLB listening is
    receptive, speaking is productive). ``RECEPTIVE`` = take in / comprehend (reading, listening);
    ``PRODUCTIVE`` = produce / perform (writing, speaking, playing); ``PROCEDURAL`` = execute a
    process or technique (a method, an algorithm); ``CONCEPTUAL`` = understand ideas + relations.
    Phase 2 keys each KC's resource + media shape off this (receptive → input material, not a
    "tutorial"). Optional — ``None`` when unclassified.
    """

    RECEPTIVE = "receptive"
    PRODUCTIVE = "productive"
    PROCEDURAL = "procedural"
    CONCEPTUAL = "conceptual"


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


class ClarifierKind(StrEnum):
    """How a clarifier question is answered (P7.5): a closed CHOICE over options, or free TEXT."""

    CHOICE = "choice"
    TEXT = "text"


class ResourceKind(StrEnum):
    """The kind of a curated external learning resource attached to a lesson phase (P7.4).

    A lesson is enriched with vetted aids the way a tutor points beyond the page: a ``VIDEO``
    (lecture/explainer), an ``ARTICLE`` (long-form/explainer), ``DOCS`` (official documentation or a
    standard), ``PRACTICE`` (exercises/quizzes/interactive), a ``TOOL`` (calculator/sandbox), or a
    ``REFERENCE`` (cheat-sheet/glossary).
    """

    VIDEO = "video"
    ARTICLE = "article"
    DOCS = "docs"
    PRACTICE = "practice"
    TOOL = "tool"
    REFERENCE = "reference"


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
    ``VOUCHED`` = a source the user supplied directly (P6.1 manual ingest) — trusted because the
    learner chose it, not because a web domain was classified.
    """

    OFFICIAL = "official"
    REPUTABLE = "reputable"
    OPEN = "open"
    BLOCKED = "blocked"
    VOUCHED = "vouched"


class SourceType(StrEnum):
    """What KIND of source a grounding chunk is (P6.0), independent of its domain authority tier.

    ``TrustTier`` says *where* a source sits in the authority order; ``source_type`` says *what it
    is* — a peer-reviewed paper vs a preprint vs official docs vs a reference work — so an unknown
    journal can still read as scholarly and a slick blog on a reputable host does not coast on its
    host. Carried on the citation for the reader; the gate that *assigns* it from page structure is
    P6.2. ``WEB`` is the unclassified open-web default.
    """

    PEER_REVIEWED = "peer_reviewed"
    PREPRINT = "preprint"
    OFFICIAL = "official"
    DATABASE = "database"
    DOCS = "docs"
    REFERENCE = "reference"
    WEB = "web"


class AcquisitionMode(StrEnum):
    """How a grounding chunk entered the corpus (P6.0) — the provenance of its acquisition.

    One corpus, three acquisition adapters writing the same shape (plan §3): ``MANUAL`` = a user
    uploaded / pasted / named it (P6.1); ``AUTO`` = the discovery agent found it on the web (P6.3);
    ``SEED`` = ingested from a source the build already fetched + vetted (P7.2 research / P7.4
    resources). The mode records which adapter the chunk arrived through, so mixed provenance stays
    auditable in one corpus.
    """

    MANUAL = "manual"
    AUTO = "auto"
    SEED = "seed"


class DiscoveryDepth(StrEnum):
    """How hard auto-discovery (P6.3) searches for a build — a pre-authorized cost ceiling.

    Chosen up front (the build can't safely pause mid-flight to ask): ``STANDARD`` is the moderate
    one-click default; ``THOROUGH`` raises the per-round search/fetch caps + the round ceiling so
    discovery corroborates more concepts across more domains, for a higher search cost. When a run
    ends with concepts still thin, the canvas says so — the learner can rebuild THOROUGH to dig in.
    """

    STANDARD = "standard"
    THOROUGH = "thorough"


class AuthorityKind(StrEnum):
    """How an entry in the editable ``source_authorities`` config (P6.2) acts on a domain.

    The authority table is a *prior, not a gate* (plan §4a): ``SPINE`` = a universally
    authoritative domain (Wikipedia, standards bodies) good across every topic; ``PACK`` = a
    per-field authority (paired with a ``SubjectField``) that only counts for runs in that field;
    ``DENYLIST`` = a known-bad domain that is never ingested or shown. A SPINE/PACK hit sets the
    domain's *tier prior* only — it never inflates the credibility score (a domain stays on-topic).
    """

    SPINE = "spine"
    PACK = "pack"
    DENYLIST = "denylist"


class SubjectField(StrEnum):
    """The subject field a course is classified into (P6.2), selecting which authority packs apply.

    Authority is topic-relative (plan §4a): PubMed is authoritative for medicine and irrelevant for
    medieval history. A run loads the matching field pack(s) + the universal spine; an unmatched
    field falls back to spine + the topic-relative signals, degrading gracefully. ``SHARED`` tags
    top multidisciplinary venues (Nature, Science, PNAS) that count across every field.
    """

    CS_ML = "cs_ml"
    MEDICINE = "medicine"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    SHARED = "shared"
