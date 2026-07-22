from enum import StrEnum


class BloomLevel(StrEnum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class CapabilityName(StrEnum):
    """A key-gated capability that has a keyed live provider and a keyless local fallback."""

    LLM = "llm"
    EMBEDDINGS = "embeddings"
    SEARCH = "search"
    VIDEO = "video"
    # The AI course cover (course-cover-images): live = OpenAI GPT Image 2, fallback = Typographic.
    # Surfaced on the live settings badge so the reader can gate cover generation on the OpenAI key;
    # NOT a per-course build tag (covers generate async, outside the build's run scope).
    COVER = "cover"


class CapabilityMode(StrEnum):
    """Whether a capability ran on its keyed provider or its keyless fallback.

    Shared by the live settings badge and the per-course build tag (keyless-fallbacks).
    """

    LIVE = "live"
    FALLBACK = "fallback"


class ComputeKind(StrEnum):
    """Where the keyless local inference runs — CPU by default, GPU when one is available.

    A keyless ("Draft") build's local model server self-selects GPU vs CPU at boot (it offloads to
    the GPU only when the host exposes one); this records which it is, for the Draft UI to surface.
    """

    CPU = "cpu"
    GPU = "gpu"


class CourseStatus(StrEnum):
    DIAGNOSING = "diagnosing"
    MAPPING = "mapping"
    SEQUENCING = "sequencing"
    AUTHORING = "authoring"
    VERIFYING = "verifying"
    REVIEW = "review"
    PUBLISHED = "published"


class ReviewGateStatus(StrEnum):
    """A publish gate's verdict on a finished course (course-review-publish).

    ``WARNING`` = an overridable defect (structure, coverage); ``CAVEAT`` = a disclosed limitation
    the learner still sees (grounding honesty); ``PASSED`` = the gate is clean.
    """

    PASSED = "passed"
    WARNING = "warning"
    CAVEAT = "caveat"


class ProgressStage(StrEnum):
    """A boundary in the course-build pipeline, emitted as a ProgressEvent.

    Ordered as the agent runs: the run starts, the request is interpreted into a brief, the target
    standard is researched (grounding the brief in real competencies), the learner is modeled (the
    frontier of what they already know), concepts are extracted, the prerequisite graph is built,
    the curriculum is designed, the grounding corpus is prepared (P6 — the evidence each claim is
    verified against: first SEEDED from the sources the research stage already fetched, then
    DISCOVERED fresh to fill the gaps), each module is authored (one event per module), claims are
    verified, learning resources are curated per lesson, coverage is verified (CQ Phase 4 — every
    researched competency is materially built, or honestly scoped out), the lesson explainer videos
    are awaited and stitched (V4), and the run completes.
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
    # The explainer-video block (V4): finalize awaits the lesson videos enqueued during authoring,
    # folding each into its lesson. Emitted once before publish, with the ready/degraded tally.
    LESSON_VIDEOS = "lesson_videos"
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


class VideoKind(StrEnum):
    """Which explainer video a job produces (plan §0): the course trailer (``SUMMARY``), the
    topic intro (``OVERVIEW``), or a per-lesson explainer (``LESSON``)."""

    SUMMARY = "summary"
    OVERVIEW = "overview"
    LESSON = "lesson"


class VideoJobStatus(StrEnum):
    """The video job's lifecycle — the queue's status machine, mirrored by the DB CHECK.

    ``QUEUED`` rows are claimable; a claim atomically flips to ``PLANNING`` (the first in-flight
    stage) and stamps the lease. The in-flight stages mirror the pipeline (plan §1.2); ``READY``,
    ``FAILED``, and ``CANCELLED`` are terminal. ``CANCELLED`` is the owner stopping a job before it
    finished: a queued job is never claimed once cancelled, and a worker aborts an in-flight render
    (killing the render subprocess) when it sees the cancel — so no compute is spent on a stopped
    video. The job row doubles as the status record the reader's hero slot polls, so these values
    are wire-visible.
    """

    QUEUED = "queued"
    PLANNING = "planning"
    CODING = "coding"
    RENDERING = "rendering"
    QA = "qa"
    VOICING = "voicing"
    ASSEMBLING = "assembling"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CoverJobStatus(StrEnum):
    """The cover-image job lifecycle — the queue's status machine, mirrored by the DB CHECK.

    ``QUEUED`` rows are claimable; a claim atomically flips to ``ART_DIRECTING`` (the first
    in-flight stage — Claude writes the house-style prompt) and stamps the lease. The in-flight
    stages mirror the cover pipeline: ``ART_DIRECTING`` → ``RENDERING`` (GPT Image 2 draws) → ``QA``
    (Claude vision checks the result) → ``UPLOADING`` (to the private course-covers bucket).
    ``READY``, ``FAILED``, and ``CANCELLED`` are terminal. ``CANCELLED`` is the owner stopping a job
    before it finished. The job row doubles as the status record the reader's cover slot polls, so
    these values are wire-visible. There is exactly one cover per course (no kind/lesson).
    """

    QUEUED = "queued"
    ART_DIRECTING = "art_directing"
    RENDERING = "rendering"
    QA = "qa"
    UPLOADING = "uploading"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CoverStylePreset(StrEnum):
    """The art-direction preset a course cover renders with (course-cover-images tunability).

    Every preset keeps the shared anti-slop discipline (no text in the image, uncluttered
    composition, generous negative space, a brand-anchored palette) — the preset varies the medium
    and mood, not the discipline. ``GENERAL`` is the house default (cover-general-preset): a premium
    enterprise editorial-infographic fused with refined 3D illustration — one hero visualization
    plus a few supporting elements on a graphite + amber dark ground, whose LIGHT twin re-themes to
    white + azure. The editorial trio keeps the original flat-illustration discipline: ``NOCTURNE``
    is the night-sky editorial look; ``BLUEPRINT`` a technical schematic / line-art look; ``AURORA``
    a soft abstract gradient with a single motif. Carried on the job's ``style_preset`` column and
    the user's ``coverStylePreset`` config key.
    """

    GENERAL = "general"
    NOCTURNE = "nocturne"
    BLUEPRINT = "blueprint"
    AURORA = "aurora"


class CoverLightMode(StrEnum):
    """How a cover's LIGHT-theme variant was produced (dual-theme covers).

    The base cover is DARK; its light twin is made one of two ways. ``RETHEME`` = an image-edit
    re-theme of the dark render (same composition — the preferred case); ``NATIVE`` = its own light
    art-direction, the fallback taken when the re-theme fails the light vision-QA bar. Carried on
    ``CoverProvenance.light_mode``, which is ``None`` when the cover has no light variant at all
    (dark-only — a light failure, or a pre-dual-theme cover).
    """

    RETHEME = "retheme"
    NATIVE = "native"


class RegenerateMode(StrEnum):
    """How a video regenerate re-enters the pipeline (explainer-video V6-T2 — the regenerate menu).

    ``FRESH`` and ``SIMPLER`` re-plan from the source (``SIMPLER`` steers the planner toward fewer
    scenes / the plainest archetypes); ``RETRY`` and ``ADD_NARRATION`` reuse the prior job's planned
    contract and re-render from there (Stage 2+), ``ADD_NARRATION`` additionally turning narration
    on — so the menu's four choices each enter the pipeline at the right node. Carried on the new
    job's ``config["regenerate"]``; absent ⇒ an ordinary fresh build.
    """

    RETRY = "retry"
    SIMPLER = "simpler"
    FRESH = "fresh"
    ADD_NARRATION = "add_narration"

    @property
    def reuses_contract(self) -> bool:
        """Whether this mode re-renders the prior contract (Stage 2+) rather than re-planning."""
        return self in (RegenerateMode.RETRY, RegenerateMode.ADD_NARRATION)
