from typing import Protocol

from .course_state_mark import CourseStateMark
from .lesson_mark import LessonMark, LessonState
from .objective_mark import ObjectiveMark


class IProgressStore(Protocol):
    """Per-user storage for learner progress (objective mastery + lesson state).

    Every method is scoped to a ``user_id``; ``None`` is the unscoped single-user posture used
    when auth is unconfigured (offline dev — the in-memory backend). With auth on, the API always
    passes a real user id and the Supabase backend's rows are additionally owner-scoped by RLS.

    Contract: ``snapshot`` returns only rows the user created; ``snapshot_all`` is the same read
    across every course (marks carry ``course_id``, so the library groups them from one query
    instead of one snapshot per course); ``set_objective`` upserts on ``understood=True`` and
    deletes on ``False`` (row presence = understood); ``set_lesson`` upserts one state per lesson
    (re-setting overwrites, idempotently) and returns the lesson's PREVIOUS state (``None`` on
    first touch) so callers can emit telemetry only on real transitions; ``touch_course`` upserts
    the (user, course) state row — stamping now() and, when given, the lesson position; a bare
    touch (no ``last_lesson_id``) must PRESERVE a previously recorded position, never erase it.
    """

    async def snapshot(
        self, *, user_id: str | None, course_id: str
    ) -> tuple[list[ObjectiveMark], list[LessonMark]]: ...

    async def snapshot_all(
        self, *, user_id: str | None
    ) -> tuple[list[ObjectiveMark], list[LessonMark]]: ...

    async def touch_course(
        self, *, user_id: str | None, course_id: str, last_lesson_id: str | None = None
    ) -> None: ...

    async def course_state(
        self, *, user_id: str | None, course_id: str
    ) -> CourseStateMark | None: ...

    async def course_states(self, *, user_id: str | None) -> list[CourseStateMark]: ...

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
    ) -> LessonState | None: ...
