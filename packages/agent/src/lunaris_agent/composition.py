import os

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
    builder = PrerequisiteGraphBuilder(ClaudePrereqJudge(worker))
    architect = ClaudeCurriculumArchitect(strong)
    author = ClaudeModuleAuthor(worker)
    grounding = retriever or _retriever_from_env() or StubEvidenceRetriever()
    verifier = Verifier(grounding, ClaudeSupportAssessor(strong))
    return Orchestrator(store, extractor, builder, architect, author, verifier)
