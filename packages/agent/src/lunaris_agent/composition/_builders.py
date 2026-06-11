from lunaris_graph import ClaudePrereqJudge, PrerequisiteGraphBuilder
from lunaris_grounding import (
    ClaudeSupportAssessor,
    IEvidenceRetriever,
    StubEvidenceRetriever,
    VerificationThresholds,
    Verifier,
)
from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.resilience import build_chat_model

from ..harness.authoring import ClaudeLessonReviser
from ..harness.runner import AgentCourseBuilder
from ..orchestrator import Orchestrator
from ..subagents.concept_extractor import ClaudeConceptExtractor
from ..subagents.curriculum_architect import ClaudeCurriculumArchitect
from ..subagents.goal_interpreter import ClaudeGoalInterpreter
from ..subagents.learner_profiler import ClaudeLearnerProfiler
from ..subagents.module_author import ClaudeModuleAuthor
from ._grounding import _discoverer_from_env, _retriever_from_env, _seeder_from_env
from ._subagents import (
    _coverage_critic_from_env,
    _curator_from_env,
    _researcher_from_env,
    _scope_polisher_from_env,
    _visual_engine_from_env,
)
from ._tiers import _strong_model, _worker_model


def build_live_prereq_builder(worker_model: str | None = None) -> PrerequisiteGraphBuilder:
    """The live prerequisite-graph builder (Claude judge) — shared by the orchestrator + MCP."""
    return PrerequisiteGraphBuilder(ClaudePrereqJudge(_worker_model(worker_model)))


def build_live_verifier(
    strong_model: str | None = None,
    retriever: IEvidenceRetriever | None = None,
) -> Verifier:
    """The live claim verifier (real retrieval + Claude assessor) — shared by orchestrator + MCP.

    Falls back to the conservative stub retriever (cuts every claim) when the corpus/embeddings
    creds are unset, so it stays runnable offline. The thresholds come from the environment
    (``LUNARIS_VERIFIER_*``), defaulting to the calibrated values.
    """
    grounding = retriever or _retriever_from_env() or StubEvidenceRetriever()
    return Verifier(
        grounding,
        ClaudeSupportAssessor(_strong_model(strong_model)),
        thresholds=VerificationThresholds.from_env(),
    )


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
    worker = _worker_model(worker_model)
    strong = _strong_model(strong_model)

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
    worker = _worker_model(worker_model)
    strong = _strong_model(strong_model)
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
