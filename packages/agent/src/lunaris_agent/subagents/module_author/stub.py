from collections.abc import Callable

from lunaris_runtime.schema import Module

from .lesson_draft import LessonDraft


class StubModuleAuthor:
    """Produces a lesson draft from a configurable function of the module.

    Lets the authoring → verification pipeline be tested without a model.
    """

    def __init__(self, fn: Callable[[Module], LessonDraft]) -> None:
        self._fn = fn

    async def author(self, module: Module) -> LessonDraft:
        return self._fn(module)
