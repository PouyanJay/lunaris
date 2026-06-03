import os
import shlex
from pathlib import Path

import structlog
from lunaris_graph import ClaudePrereqJudge, PrerequisiteGraphBuilder
from lunaris_grounding import (
    ClaudeSupportAssessor,
    IEvidenceRetriever,
    PgVectorRetriever,
    StubEvidenceRetriever,
    SupabaseCorpusStore,
    TavilySearchProvider,
    TrafilaturaContentExtractor,
    Verifier,
    VoyageEmbedder,
)
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.resilience import (
    LLM_MAX_RETRIES,
    LLM_REQUEST_TIMEOUT_S,
    get_llm_rate_limiter,
)

from .harness.authoring import ClaudeLessonReviser
from .harness.runner import AgentCourseBuilder
from .orchestrator import Orchestrator
from .subagents.concept_extractor import ClaudeConceptExtractor
from .subagents.curriculum_architect import ClaudeCurriculumArchitect
from .subagents.goal_interpreter import ClaudeGoalInterpreter
from .subagents.learner_profiler import ClaudeLearnerProfiler
from .subagents.module_author import ClaudeModuleAuthor
from .subagents.standard_researcher import (
    ClaudeStandardResearcher,
    IStandardResearcher,
    StubStandardResearcher,
)
from .subagents.visual_agent import (
    ClaudeVisualGenerator,
    MermaidRenderer,
    PassthroughDiagramRenderer,
    VisualEngine,
)

logger = structlog.get_logger()

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"
_DEFAULT_STRONG = "claude-opus-4-8"


def _retriever_from_env() -> IEvidenceRetriever | None:
    """Build the real pgvector retriever iff the corpus + embeddings creds are present.

    Returns ``None`` (→ the verifier falls back to the conservative stub that cuts every
    claim) when Supabase or the embeddings key is unset, so the pipeline still runs offline.
    """
    if (
        os.getenv("SUPABASE_URL")
        and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        and os.getenv("EMBEDDINGS_API_KEY")
    ):
        return PgVectorRetriever(VoyageEmbedder(), SupabaseCorpusStore())
    logger.info("grounding_retriever_stubbed", reason="supabase/embeddings creds unset")
    return None


def _researcher_from_env(worker_model: str) -> IStandardResearcher:
    """Build the live standard researcher iff a search key is present, else the stub.

    The real researcher grounds the brief over the shared Tavily search + Trafilatura extraction
    adapters (worker tier for distillation). With no ``SEARCH_API_KEY`` it returns the stub, so
    research degrades honestly to UNAVAILABLE and the no-key CI path stays deterministic.
    """
    if os.getenv("SEARCH_API_KEY"):
        return ClaudeStandardResearcher(
            worker_model, TavilySearchProvider(), TrafilaturaContentExtractor()
        )
    logger.info("standard_researcher_stubbed", reason="SEARCH_API_KEY unset")
    return StubStandardResearcher()


def _visual_engine_from_env(worker_model: str) -> VisualEngine:
    """Wire the live visual engine, choosing the renderer from the environment.

    The generator (Claude, worker tier) always proposes a branded ``VisualSpec`` plus a Mermaid
    fallback. The renderer only gates the *source* path:
    - ``LUNARIS_MERMAID_SCRIPT`` set → the real :class:`MermaidRenderer` shells out to the
      beautiful-mermaid skill's ``render.ts`` (``LUNARIS_VISUAL_DIR`` = SVG output dir, default
      ``.visuals``; ``LUNARIS_MERMAID_RUNTIME`` = the invocation prefix, default ``bun run``,
      e.g. ``npx tsx``), validating each diagram to an SVG before it ships.
    - unset → the :class:`PassthroughDiagramRenderer`, which validates the source syntactically and
      ships it un-rendered (the web draws from the spec or the raw source, never the SVG path).

    Either way a course gets its branded visuals; the render toolchain is an enhancement, never a
    hard dependency. Always returns an engine (which still declines decorative diagrams itself).
    """
    script = os.getenv("LUNARIS_MERMAID_SCRIPT")
    if not script:
        logger.info("visual_engine_passthrough", reason="LUNARIS_MERMAID_SCRIPT unset")
        return VisualEngine(ClaudeVisualGenerator(worker_model), PassthroughDiagramRenderer())
    output_dir = Path(os.getenv("LUNARIS_VISUAL_DIR", ".visuals"))
    runtime_env = os.getenv("LUNARIS_MERMAID_RUNTIME")
    runtime = tuple(shlex.split(runtime_env)) if runtime_env else None
    renderer = (
        MermaidRenderer(Path(script), output_dir, runtime=runtime)
        if runtime
        else MermaidRenderer(Path(script), output_dir)
    )
    return VisualEngine(ClaudeVisualGenerator(worker_model), renderer)


def build_live_prereq_builder(worker_model: str | None = None) -> PrerequisiteGraphBuilder:
    """The live prerequisite-graph builder (Claude judge) — shared by the orchestrator + MCP."""
    worker = worker_model or os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER)
    return PrerequisiteGraphBuilder(ClaudePrereqJudge(worker))


def build_live_verifier(
    strong_model: str | None = None,
    retriever: IEvidenceRetriever | None = None,
) -> Verifier:
    """The live claim verifier (real retrieval + Claude assessor) — shared by orchestrator + MCP.

    Falls back to the conservative stub retriever (cuts every claim) when the corpus/embeddings
    creds are unset, so it stays runnable offline.
    """
    strong = strong_model or os.getenv("LUNARIS_MODEL_STRONG", _DEFAULT_STRONG)
    grounding = retriever or _retriever_from_env() or StubEvidenceRetriever()
    return Verifier(grounding, ClaudeSupportAssessor(strong))


def build_orchestrator(
    store: CourseStore,
    *,
    worker_model: str | None = None,
    strong_model: str | None = None,
    retriever: IEvidenceRetriever | None = None,
) -> Orchestrator:
    """Composition root: wire the live subagents from env into an Orchestrator.

    Worker tier (``LUNARIS_MODEL_WORKER``) handles bulk extraction/judging/authoring;
    the strong tier (``LUNARIS_MODEL_STRONG``) handles curriculum architecture and acts
    as the INDEPENDENT support assessor (a different tier than the author, so it doesn't
    share blind spots). The retriever is the real Supabase pgvector retriever (D2) when the
    corpus + embeddings creds are set; otherwise it falls back to the conservative stub
    (every claim cut). Pass an explicit ``retriever`` to override either path (e.g. tests).
    """
    worker = worker_model or os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER)
    strong = strong_model or os.getenv("LUNARIS_MODEL_STRONG", _DEFAULT_STRONG)

    extractor = ClaudeConceptExtractor(worker)
    builder = build_live_prereq_builder(worker)
    architect = ClaudeCurriculumArchitect(strong)
    author = ClaudeModuleAuthor(worker)
    verifier = build_live_verifier(strong, retriever)
    visual_engine = _visual_engine_from_env(worker)
    return Orchestrator(
        store, extractor, builder, architect, author, verifier, visual_engine=visual_engine
    )


def build_agent_course_builder(
    store: CourseStore,
    *,
    worker_model: str | None = None,
    strong_model: str | None = None,
    retriever: IEvidenceRetriever | None = None,
) -> AgentCourseBuilder:
    """Composition root for the AGENT pipeline: a real deep agent over the live subagents/moats.

    Replaces ``build_orchestrator`` with a ``create_deep_agent`` harness that plans the build and
    delegates lesson authoring to the author→verify→revise subagent. Same tier split as the
    orchestrator: the STRONG tier is the agent planner + curriculum architect + independent support
    assessor; the WORKER tier handles extraction, the prereq judge, and lesson authoring/revision.
    The retriever follows the same env-gated path as the orchestrator (real pgvector when creds are
    set, conservative stub otherwise). ``opus-4`` rejects ``temperature``, so none is passed. The
    planner client is built explicitly (not as a bare model id) so it carries a request timeout —
    otherwise ``create_deep_agent`` would build an un-timed client and a stalled socket would hang
    the whole run. ``stream_tokens=True`` because this planner is a real streaming model: the agent
    reasoning streams token-by-token to the UI (the no-key path keeps the deterministic beats).
    """
    from langchain_anthropic import ChatAnthropic

    worker = worker_model or os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER)
    strong = strong_model or os.getenv("LUNARIS_MODEL_STRONG", _DEFAULT_STRONG)
    planner = ChatAnthropic(
        model=strong,
        default_request_timeout=LLM_REQUEST_TIMEOUT_S,
        max_retries=LLM_MAX_RETRIES,
        rate_limiter=get_llm_rate_limiter(),
    )
    return AgentCourseBuilder(
        planner,
        store,
        interpreter=ClaudeGoalInterpreter(worker),
        profiler=ClaudeLearnerProfiler(worker),
        researcher=_researcher_from_env(worker),
        extractor=ClaudeConceptExtractor(worker),
        builder=build_live_prereq_builder(worker),
        architect=ClaudeCurriculumArchitect(strong),
        reviser=ClaudeLessonReviser(worker),
        verifier=build_live_verifier(strong, retriever),
        visual_engine=_visual_engine_from_env(worker),
        stream_tokens=True,
    )
