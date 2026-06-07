"""The authoring loop's view of a module author: a first pass plus targeted revision.

The author→verify→revise loop needs more than one-shot authoring — when the verifier cuts a
claim, it must ask the author to *revise* the lesson with that feedback in hand. ``ILessonReviser``
adds that ``revise`` capability alongside the first-pass ``author``; the existing one-shot
``IModuleAuthor`` stays unchanged (the orchestrator keeps using it directly).
"""

from collections.abc import Sequence
from typing import Protocol

from lunaris_runtime.schema import CourseBrief, Module

from ...subagents.module_author import LessonDraft


class ILessonReviser(Protocol):
    """Authors a module's lesson and can revise it given the claims the verifier cut.

    ``brief``/``frontier`` (the run's interpreted request + the learner's frontier) personalize the
    arc — passed through to the author so the lesson is aimed at the module's competency, pitched at
    the level, and scoped above the frontier (P7.3). Both are optional: omitting them yields the
    generic arc, keeping the loop usable without an interpreted brief. ``grounded_evidence`` (CQ
    Phase 1.5) is the corpus evidence retrieved for the module's KCs / the cut claims, rendered as
    prompt text, so the author writes claims the evidence supports rather than from memory; empty
    means no grounding was available.
    """

    async def author(
        self,
        module: Module,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
        grounded_evidence: str = "",
    ) -> LessonDraft:
        """Author the module's first-pass lesson arc."""
        ...

    async def revise(
        self,
        module: Module,
        cut_claims: Sequence[str],
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
        grounded_evidence: str = "",
    ) -> LessonDraft:
        """Re-author the lesson, grounding or replacing the claims the verifier cut, arc intact."""
        ...
