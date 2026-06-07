"""A deterministic ``ILessonReviser`` for the no-key path — scripts the loop's behaviour.

Tests drive the author→verify→revise loop by configuring exactly what the author returns on the
first pass and on each revision, so convergence, early-stop, and triage can be asserted without a
model or network.
"""

from collections.abc import Callable, Sequence

from lunaris_runtime.schema import CourseBrief, Module

from ...subagents.module_author import LessonDraft


class StubLessonReviser:
    """Returns scripted lesson drafts: one for the first pass, one per revision call.

    ``author_fn`` produces the first-pass draft for a module. ``revise_fn`` produces a revised
    draft given the module and the cut claims; it also receives the revision count (1-based) so a
    test can model "fixed on the second attempt", "never fixed", or "stops improving". ``brief``/
    ``frontier``/``grounded_evidence`` are accepted (to satisfy ``ILessonReviser``) but ignored —
    the scripted functions are the test's control; arc personalization + grounding are covered by
    ``build_authoring_prompt`` and the loop's retrieval tests.
    """

    def __init__(
        self,
        author_fn: Callable[[Module], LessonDraft],
        revise_fn: Callable[[Module, Sequence[str], int], LessonDraft],
    ) -> None:
        self._author_fn = author_fn
        self._revise_fn = revise_fn
        self._revisions: dict[str, int] = {}

    async def author(
        self,
        module: Module,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
        grounded_evidence: str = "",
    ) -> LessonDraft:
        return self._author_fn(module)

    async def revise(
        self,
        module: Module,
        cut_claims: Sequence[str],
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
        grounded_evidence: str = "",
    ) -> LessonDraft:
        self._revisions[module.id] = self._revisions.get(module.id, 0) + 1
        return self._revise_fn(module, cut_claims, self._revisions[module.id])
