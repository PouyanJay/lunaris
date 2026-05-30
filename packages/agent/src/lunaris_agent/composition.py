import os

from lunaris_graph import ClaudePrereqJudge, PrerequisiteGraphBuilder
from lunaris_runtime.persistence import CourseStore

from .orchestrator import Orchestrator
from .subagents.concept_extractor import ClaudeConceptExtractor

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"


def build_orchestrator(store: CourseStore, *, worker_model: str | None = None) -> Orchestrator:
    """Composition root: wire the live subagents from env into an Orchestrator.

    Reads ``LUNARIS_MODEL_WORKER`` for the extraction/judging tier (D1). Never
    instantiates dependencies inside the classes that use them.
    """
    worker = worker_model or os.getenv("LUNARIS_MODEL_WORKER", _DEFAULT_WORKER)
    extractor = ClaudeConceptExtractor(worker)
    builder = PrerequisiteGraphBuilder(ClaudePrereqJudge(worker))
    return Orchestrator(store, extractor, builder)
