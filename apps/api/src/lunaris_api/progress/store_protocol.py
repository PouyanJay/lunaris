from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

LessonState = Literal["in_progress", "done"]

# Objectives carry no id in the course schema, so a mark is keyed by the objective's position in
# its module's objectives array — stable across reads of the same course payload (a rebuild that
# reorders objectives orphans the mark, which is acceptable: progress is per built course).


@dataclass(frozen=True)
class ObjectiveMark:
    """One understood objective: the learner marked module ``module_id``'s ``objective_index``."""

    course_id: str
    module_id: str
    objective_index: int
    understood_at: datetime


@dataclass(frozen=True)
class LessonMark:
    """A lesson's learner state — ``in_progress`` on first open, ``done`` on completion."""

    course_id: str
    lesson_id: str
    state: LessonState
    updated_at: datetime


class IProgressStore(Protocol):
    """Per-user storage for learner progress (objective mastery + lesson state).

    Every method is scoped to a ``user_id``; ``None`` is the unscoped single-user posture used
    when auth is unconfigured (offline dev — the in-memory backend). With auth on, the API always
    passes a real user id and the Supabase backend's rows are additionally owner-scoped by RLS.

    Contract: ``snapshot`` returns only rows the user created; ``set_objective`` upserts on
    ``understood=True`` and deletes on ``False`` (row presence = understood); ``set_lesson``
    upserts one state per lesson (re-setting overwrites, idempotently).
    """

    async def snapshot(
        self, *, user_id: str | None, course_id: str
    ) -> tuple[list[ObjectiveMark], list[LessonMark]]: ...

    async def set_objective(
        self,
        *,
        user_id: str | None,
        course_id: str,
        module_id: str,
        objective_index: int,
        understood: bool,
    ) -> None: ...

    async def set_lesson(
        self, *, user_id: str | None, course_id: str, lesson_id: str, state: LessonState
    ) -> None: ...
