from typing import Protocol

from lunaris_runtime.schema import CourseBrief, Module

from .lesson_draft import LessonDraft


class IModuleAuthor(Protocol):
    """Authors a module's lesson as a learning arc — entry expectations, the Merrill cycle (activate
    → demonstrate → apply → integrate), and a self-check — extracting every factual sentence as a
    claim for the verifier. Owns ``module.lessons``. Swappable (live model vs. test stub).

    When ``brief``/``frontier`` are present the arc is personalized — aimed at the module's
    competency, pitched at the brief's level, scoped above the frontier, written in the requested
    voice; omitting both preserves the generic arc (the legacy / orchestrator path).
    """

    async def author(
        self,
        module: Module,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> LessonDraft: ...
