import os

from lunaris_graph import ClaudePrereqJudge, PrerequisiteGraphBuilder
from lunaris_runtime.persistence import CourseStore

from .orchestrator import Orchestrator
from .subagents.concept_extractor import ClaudeConceptExtractor
from .subagents.curriculum_architect import ClaudeCurriculumArchitect

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"
_DEFAULT_STRONG = "claude-opus-4-8"


def build_orchestrator(
    store: CourseStore,
    *,
    worker_model: str | None = None,
    strong_model: str | None = None,
) -> Orchestrator:
    """Composition root: wire the live subagents from env into an Orchestrator.

    Worker tier (``LUNARIS_MODEL_WORKER``) handles bulk extraction + pairwise judging;
    the strong tier (``LUNARIS_MODEL_STRONG``) handles the curriculum architecture (D1).
    Never instantiates dependencies inside the classes that use them.
    """
    worker = worker_model or os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER)
    strong = strong_model or os.getenv("LUNARIS_MODEL_STRONG", _DEFAULT_STRONG)
    extractor = ClaudeConceptExtractor(worker)
    builder = PrerequisiteGraphBuilder(ClaudePrereqJudge(worker))
    architect = ClaudeCurriculumArchitect(strong)
    return Orchestrator(store, extractor, builder, architect)
