from datetime import UTC, datetime

from .course_state_mark import CourseStateMark
from .lesson_mark import LessonMark, LessonState
from .objective_mark import ObjectiveMark


class InMemoryProgressStore:
    """The no-DB progress store (offline dev / hermetic tests): plain dicts keyed by user.

    ``None`` user_id is the single-user posture — all unauthenticated progress shares one bucket,
    mirroring how the file-backed stores behave when auth is off. Process-lifetime only.
    """

    def __init__(self) -> None:
        self._objectives: dict[tuple[str | None, str, str, int], ObjectiveMark] = {}
        self._lessons: dict[tuple[str | None, str, str], LessonMark] = {}
        self._course_states: dict[tuple[str | None, str], CourseStateMark] = {}

    async def snapshot(
        self, *, user_id: str | None, course_id: str
    ) -> tuple[list[ObjectiveMark], list[LessonMark]]:
        objectives = [
            mark
            for (owner, course, _module, _index), mark in self._objectives.items()
            if owner == user_id and course == course_id
        ]
        lessons = [
            mark
            for (owner, course, _lesson), mark in self._lessons.items()
            if owner == user_id and course == course_id
        ]
        return objectives, lessons

    async def snapshot_all(
        self, *, user_id: str | None
    ) -> tuple[list[ObjectiveMark], list[LessonMark]]:
        objectives = [mark for (owner, *_), mark in self._objectives.items() if owner == user_id]
        lessons = [mark for (owner, *_), mark in self._lessons.items() if owner == user_id]
        return objectives, lessons

    async def set_objective(
        self,
        *,
        user_id: str | None,
        course_id: str,
        module_id: str,
        objective_index: int,
        understood: bool,
    ) -> None:
        key = (user_id, course_id, module_id, objective_index)
        if understood:
            self._objectives[key] = ObjectiveMark(
                course_id=course_id,
                module_id=module_id,
                objective_index=objective_index,
                understood_at=datetime.now(UTC),
            )
        else:
            self._objectives.pop(key, None)

    async def set_lesson(
        self, *, user_id: str | None, course_id: str, lesson_id: str, state: LessonState
    ) -> None:
        self._lessons[(user_id, course_id, lesson_id)] = LessonMark(
            course_id=course_id,
            lesson_id=lesson_id,
            state=state,
            updated_at=datetime.now(UTC),
        )

    async def touch_course(
        self, *, user_id: str | None, course_id: str, last_lesson_id: str | None = None
    ) -> None:
        key = (user_id, course_id)
        previous = self._course_states.get(key)
        # A bare touch keeps the recorded reading position — only a lesson open moves it.
        preserved = (
            last_lesson_id
            if last_lesson_id is not None
            else (previous.last_lesson_id if previous else None)
        )
        self._course_states[key] = CourseStateMark(
            course_id=course_id, last_opened_at=datetime.now(UTC), last_lesson_id=preserved
        )

    async def course_state(self, *, user_id: str | None, course_id: str) -> CourseStateMark | None:
        return self._course_states.get((user_id, course_id))

    async def course_states(self, *, user_id: str | None) -> list[CourseStateMark]:
        return [mark for (owner, _), mark in self._course_states.items() if owner == user_id]
