import os

from lunaris_graph import ClaudePrereqJudge, PrerequisiteGraphBuilder
from lunaris_grounding import (
    ClaudeSupportAssessor,
    IEvidenceRetriever,
    StubEvidenceRetriever,
    Verifier,
)
from lunaris_runtime.persistence import CourseStore

from .orchestrator import Orchestrator
from .subagents.concept_extractor import ClaudeConceptExtractor
from .subagents.curriculum_architect import ClaudeCurriculumArchitect
from .subagents.module_author import ClaudeModuleAuthor

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"
_DEFAULT_STRONG = "claude-opus-4-8"


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
    share blind spots). The retriever defaults to a stub until the Supabase pgvector
    corpus (D2) is wired — pass a real ``IEvidenceRetriever`` to ground against a corpus.
    """
    worker = worker_model or os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER)
    strong = strong_model or os.getenv("LUNARIS_MODEL_STRONG", _DEFAULT_STRONG)

    extractor = ClaudeConceptExtractor(worker)
    builder = PrerequisiteGraphBuilder(ClaudePrereqJudge(worker))
    architect = ClaudeCurriculumArchitect(strong)
    author = ClaudeModuleAuthor(worker)
    verifier = Verifier(retriever or StubEvidenceRetriever(), ClaudeSupportAssessor(strong))
    return Orchestrator(store, extractor, builder, architect, author, verifier)
