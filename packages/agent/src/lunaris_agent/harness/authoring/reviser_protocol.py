"""The authoring loop's view of a module author: a first pass plus targeted revision.

The author→verify→revise loop needs more than one-shot authoring — when the verifier cuts a
claim, it must ask the author to *revise* the lesson with that feedback in hand. ``ILessonReviser``
adds that ``revise`` capability alongside the first-pass ``author``; the existing one-shot
``IModuleAuthor`` stays unchanged (the orchestrator keeps using it directly).
"""

from collections.abc import Sequence
from typing import Protocol

from lunaris_runtime.schema import Module

from ...subagents.module_author import LessonDraft


class ILessonReviser(Protocol):
    """Authors a module's lesson and can revise it given the claims the verifier cut."""

    async def author(self, module: Module) -> LessonDraft:
        """Author the module's first-pass Merrill lesson."""
        ...

    async def revise(self, module: Module, cut_claims: Sequence[str]) -> LessonDraft:
        """Re-author the lesson, grounding or replacing the claims the verifier cut."""
        ...
