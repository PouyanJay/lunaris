import os
import shlex
from pathlib import Path

import structlog
from lunaris_graph import ClaudePrereqJudge, PrerequisiteGraphBuilder
from lunaris_grounding import (
    ClaudeSupportAssessor,
    CorpusIngestor,
    CredibilityScorer,
    DuckDuckGoSearchProvider,
    IEmbedder,
    IEvidenceRetriever,
    ISearchProvider,
    IVideoSource,
    LocalEmbedder,
    OpenAlexScholarlyRegistry,
    PgVectorRetriever,
    SearchVideoSource,
    StubEvidenceRetriever,
    SupabaseCorpusStore,
    SupabaseSourceAuthorityStore,
    TavilySearchProvider,
    TrafilaturaContentExtractor,
    Verifier,
    VoyageEmbedder,
    YouTubeVideoSource,
)
from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.resilience import build_chat_model
from lunaris_runtime.run_config import resolve_config

from .coverage_critic import (
    ClaudeCoverageCritic,
    DeterministicCoverageCritic,
    ICoverageCritic,
)
from .harness.authoring import ClaudeLessonReviser
from .harness.discovery import (
    ClaudeRelevanceJudge,
    IGroundingDiscoverer,
    StubGroundingDiscoverer,
    SubgraphGroundingDiscoverer,
)
from .harness.runner import AgentCourseBuilder
from .harness.seeding import GroundingSeeder, IGroundingSeeder, StubGroundingSeeder
from .orchestrator import Orchestrator
from .subagents.concept_extractor import ClaudeConceptExtractor
from .subagents.curriculum_architect import ClaudeCurriculumArchitect
from .subagents.goal_interpreter import ClaudeGoalInterpreter
from .subagents.learner_profiler import ClaudeLearnerProfiler
from .subagents.module_author import ClaudeModuleAuthor
from .subagents.resource_curator import (
    ClaudeQueryTranslator,
    ClaudeResourceCurator,
    IResourceCurator,
)
from .subagents.scope_polisher import ClaudeScopePolisher, IScopePolisher
from .subagents.standard_researcher import (
    ClaudeStandardResearcher,
    IStandardResearcher,
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


def _embedder_from_env() -> IEmbedder:
    """The embedder for a run: Voyage when its key is set, else the keyless local fallback (nano).

    Embeddings are no longer key-gated: with no key the run uses the local nano fallback (over an
    OpenAI-compatible endpoint), so grounding still works keyless. Nano and Voyage are different
    vector spaces, so a corpus ingests + queries under one embedder; a switch means re-grounding.
    """
    if resolve_secret("EMBEDDINGS_API_KEY"):
        return VoyageEmbedder()
    logger.info("embedder_local_fallback", reason="EMBEDDINGS_API_KEY unset")
    return LocalEmbedder()


def _retriever_from_env() -> IEvidenceRetriever | None:
    """Build the real pgvector retriever iff the Supabase corpus is present.

    Embeddings are keyless (Voyage when keyed, else the local nano fallback), so this gates only on
    the Supabase corpus store. Returns ``None`` (→ the verifier falls back to the conservative stub
    that cuts every claim) only when Supabase is unset, so the pipeline still runs corpus-less.
    """
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        return PgVectorRetriever(_embedder_from_env(), SupabaseCorpusStore())
    logger.info("grounding_retriever_stubbed", reason="supabase corpus unset")
    return None


def _discoverer_from_env(worker_model: str) -> IGroundingDiscoverer:
    """Build the live grounding discoverer iff the Supabase corpus is present (P6.3).

    Search + embeddings are keyless (DuckDuckGo / local nano when their keys are unset), so it
    gates only on the Supabase corpus (the store the verifier retrieves from). Without it the stub
    is returned (no source ingested), so the corpus-less path stays deterministic and claims fall
    to REVIEW. The discovery sub-graph grades each source with the credibility scorer — backed by
    the seeded authorities table + the live OpenAlex registry (keyless; optional ``OPENALEX_EMAIL``
    for its polite pool), which floors an unknown host serving a real paper to REPUTABLE — and drops
    off-topic ones with a label-blind worker-tier judge, so machine-found evidence is graded, not
    just gathered.
    """
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        scorer = CredibilityScorer(
            SupabaseSourceAuthorityStore(),
            registry=OpenAlexScholarlyRegistry(mailto=os.getenv("OPENALEX_EMAIL")),
        )
        return SubgraphGroundingDiscoverer(
            _search_provider_from_env(),
            TrafilaturaContentExtractor(),
            scorer,
            ClaudeRelevanceJudge(worker_model),
            CorpusIngestor(_embedder_from_env(), SupabaseCorpusStore()),
        )
    logger.info("grounding_discoverer_stubbed", reason="supabase corpus unset")
    return StubGroundingDiscoverer()


def _seeder_from_env() -> IGroundingSeeder:
    """Build the live grounding seeder iff the Supabase corpus is present (P6.4).

    Embeddings are keyless (local nano when no Voyage key), so seeding gates only on the Supabase
    corpus (to ingest into the same store the verifier retrieves from); it needs no search key,
    since it reuses pages the research stage already fetched. Its ingestor carries the credibility
    scorer (backed by the seeded authorities table + the live OpenAlex registry), so each seed is
    graded through the SAME gate as an auto-discovered source: seeded is not the same as trusted.
    Without the corpus it returns the stub (nothing ingested), so the corpus-less path stays
    deterministic and claims fall to the verifier's existing behaviour.
    """
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        scorer = CredibilityScorer(
            SupabaseSourceAuthorityStore(),
            registry=OpenAlexScholarlyRegistry(mailto=os.getenv("OPENALEX_EMAIL")),
        )
        return GroundingSeeder(
            CorpusIngestor(_embedder_from_env(), SupabaseCorpusStore(), scorer=scorer)
        )
    logger.info("grounding_seeder_stubbed", reason="supabase corpus unset")
    return StubGroundingSeeder()


def _search_provider_from_env() -> ISearchProvider:
    """The web-search provider for a run: Tavily when its key is set, else keyless DuckDuckGo.

    Search is no longer key-gated — with no ``SEARCH_API_KEY`` the run searches via DuckDuckGo (no
    key), so research / discovery / resource curation still run keyless instead of stubbing out.
    """
    if resolve_secret("SEARCH_API_KEY"):
        return TavilySearchProvider()
    logger.info("search_provider_duckduckgo_fallback", reason="SEARCH_API_KEY unset")
    return DuckDuckGoSearchProvider()


def _researcher_from_env(worker_model: str) -> IStandardResearcher:
    """The standard researcher — always live now that search is keyless (Tavily or DuckDuckGo).

    Grounds the brief over the selected search provider + Trafilatura extraction (worker tier for
    distillation). The keyless path uses DuckDuckGo, so research no longer degrades to UNAVAILABLE.
    """
    return ClaudeStandardResearcher(
        worker_model, _search_provider_from_env(), TrafilaturaContentExtractor()
    )


def _video_source_from_env() -> IVideoSource:
    """The video source for resource curation: YouTube when keyed, else the shared-search fallback.

    With a ``YOUTUBE_API_KEY`` set, videos come from the YouTube Data API (guaranteed-video results
    + channel); without one, every video query routes through the shared ``ISearchProvider`` (itself
    keyless via DuckDuckGo when there's no Tavily key) so a video is still found + vetted, just
    without YouTube's metadata.
    """
    if resolve_secret("YOUTUBE_API_KEY"):
        return YouTubeVideoSource()
    logger.info("video_source_search_fallback", reason="YOUTUBE_API_KEY unset")
    return SearchVideoSource(_search_provider_from_env())


def _curator_from_env(worker_model: str) -> IResourceCurator:
    """Build the resource curator — always live now that search is keyless (P7.4).

    Mirrors the researcher: the live curator finds + vets resources over the selected search
    provider, plus an ``IVideoSource`` (worker tier for the relevance judge). The query translator
    (CQ Phase 2, worker tier) rewrites each competency into domain vernacular before the search.
    Search is keyless (Tavily or DuckDuckGo), so curation is always live rather than stubbing.
    """
    return ClaudeResourceCurator(
        worker_model,
        _search_provider_from_env(),
        _video_source_from_env(),
        translator=ClaudeQueryTranslator(worker_model),
    )


def _scope_polisher_from_env(worker_model: str) -> IScopePolisher | None:
    """Build the live scope-band polisher iff an Anthropic key is present, else ``None`` (CQ P3.1).

    The polish step refines only the wording of the scope band's does/doesn't lines (worker tier);
    its facts are owned by the deterministic estimator and re-asserted in code, so the model can
    sharpen the copy but never change the effort or invent a promise. ``None`` (no key) ships the
    deterministic band unchanged — the offline path stays byte-for-byte stable, no LLM call made.
    """
    if resolve_secret("ANTHROPIC_API_KEY"):
        return ClaudeScopePolisher(worker_model)
    logger.info("scope_polisher_disabled", reason="ANTHROPIC_API_KEY unset")
    return None


def _coverage_critic_from_env(strong_model: str) -> ICoverageCritic:
    """Build the coverage critic (CQ Phase 4.2): the LLM judge when keyed, else the fail-safe.

    The gate always runs. With an ``ANTHROPIC_API_KEY`` the primary is the ``ClaudeCoverageCritic``
    (strong tier — coverage is a judgement call, and it already degrades to the deterministic check
    on any failure). Without a key it is the ``DeterministicCoverageCritic`` directly — a structural
    check that needs no model, so a keyless build still gets an honest coverage gate. Either way an
    unresearched brief yields a clean report (nothing was promised), so the offline suite is stable.
    """
    if resolve_secret("ANTHROPIC_API_KEY"):
        return ClaudeCoverageCritic(strong_model)
    logger.info("coverage_critic_keyless", reason="ANTHROPIC_API_KEY unset")
    return DeterministicCoverageCritic()


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
    worker = worker_model or resolve_config("LUNARIS_MODEL_WORKER") or _DEFAULT_WORKER
    return PrerequisiteGraphBuilder(ClaudePrereqJudge(worker))


def build_live_verifier(
    strong_model: str | None = None,
    retriever: IEvidenceRetriever | None = None,
) -> Verifier:
    """The live claim verifier (real retrieval + Claude assessor) — shared by orchestrator + MCP.

    Falls back to the conservative stub retriever (cuts every claim) when the corpus/embeddings
    creds are unset, so it stays runnable offline.
    """
    strong = strong_model or resolve_config("LUNARIS_MODEL_STRONG") or _DEFAULT_STRONG
    grounding = retriever or _retriever_from_env() or StubEvidenceRetriever()
    return Verifier(grounding, ClaudeSupportAssessor(strong))


def build_orchestrator(
    store: ICourseStore,
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
    worker = worker_model or resolve_config("LUNARIS_MODEL_WORKER") or _DEFAULT_WORKER
    strong = strong_model or resolve_config("LUNARIS_MODEL_STRONG") or _DEFAULT_STRONG

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
    store: ICourseStore,
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
    the whole run. It routes through ``build_chat_model`` so it picks up the current run's
    BYOK Anthropic key (the tenant's own) alongside the shared hardening. ``stream_tokens=True``
    because this planner is a real streaming model: the agent reasoning streams token-by-token to
    the UI (the no-key path keeps the deterministic beats).

    BYOK invariant: this factory is called per run inside the caller's credential scope, so the
    adapters it builds (which read their key lazily, on first call) resolve the CURRENT tenant's
    key. Each run gets a fresh set of adapters — never reuse a built builder across runs, or a
    cached client would serve the first tenant's key to the next.
    """
    worker = worker_model or resolve_config("LUNARIS_MODEL_WORKER") or _DEFAULT_WORKER
    strong = strong_model or resolve_config("LUNARIS_MODEL_STRONG") or _DEFAULT_STRONG
    planner = build_chat_model(strong)
    # Keyless (Draft) builds run the tools in a fixed, code-enforced order instead of the autonomous
    # planner — a small local model can't reliably orchestrate the multi-tool build. Gated on the
    # SAME no-Anthropic-key signal as ``build_chat_model``/``_is_keyless_llm`` (this factory runs in
    # the run's credential scope), so a keyed build keeps the full agent harness, never scripted.
    keyless = not resolve_secret("ANTHROPIC_API_KEY")
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
        curator=_curator_from_env(worker),
        seeder=_seeder_from_env(),
        discoverer=_discoverer_from_env(worker),
        verifier=build_live_verifier(strong, retriever),
        coverage_critic=_coverage_critic_from_env(strong),
        visual_engine=_visual_engine_from_env(worker),
        scope_polisher=_scope_polisher_from_env(worker),
        # The scripted (keyless) path never token-streams (no planner loop); only the keyed agent
        # path streams the planner's reasoning token-by-token.
        stream_tokens=not keyless,
        scripted=keyless,
    )
