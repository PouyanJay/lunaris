from collections.abc import Callable

from lunaris_runtime.schema import CourseBrief, Module

from .lesson_draft import LessonDraft


class StubModuleAuthor:
    """Produces a lesson draft from a configurable function of the module.

    Lets the authoring → verification pipeline be tested without a model. ``brief``/``frontier`` are
    accepted (to satisfy ``IModuleAuthor``) but ignored — the configured function is the test's
    control over the output; the prompt personalization is covered by ``build_authoring_prompt``.
    """

    def __init__(self, fn: Callable[[Module], LessonDraft]) -> None:
        self._fn = fn

    async def author(
        self,
        module: Module,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> LessonDraft:
        return self._fn(module)
