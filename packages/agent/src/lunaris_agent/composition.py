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
    Verifier,
    VoyageEmbedder,
)
from lunaris_runtime.persistence import CourseStore

from .orchestrator import Orchestrator
from .subagents.concept_extractor import ClaudeConceptExtractor
from .subagents.curriculum_architect import ClaudeCurriculumArchitect
from .subagents.module_author import ClaudeModuleAuthor
from .subagents.visual_agent import ClaudeVisualGenerator, MermaidRenderer, VisualEngine

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


def _visual_engine_from_env(worker_model: str) -> VisualEngine | None:
    """Wire the live visual engine iff the beautiful-mermaid render script is configured.

    ``LUNARIS_MERMAID_SCRIPT`` points at the skill's ``render.ts``; ``LUNARIS_VISUAL_DIR``
    is where rendered SVGs land (default ``.visuals``); ``LUNARIS_MERMAID_RUNTIME`` is the
    invocation prefix (default ``bun run``; e.g. ``npx tsx``). Without the script set we skip
    visuals entirely (return ``None``) — diagrams are optional, never a hard dependency.
    """
    script = os.getenv("LUNARIS_MERMAID_SCRIPT")
    if not script:
        logger.info("visual_engine_disabled", reason="LUNARIS_MERMAID_SCRIPT unset")
        return None
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
