from typing import Protocol

from lunaris_runtime.schema import Module

from .lesson_draft import LessonDraft


class IModuleAuthor(Protocol):
    """Authors a module's lesson through the Merrill cycle (activate → demonstrate →
    apply → integrate), extracting every factual sentence as a claim for the verifier.
    Owns ``module.lessons``. Swappable (live model vs. test stub).
    """

    async def author(self, module: Module) -> LessonDraft: ...
