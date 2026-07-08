from datetime import UTC, datetime

import structlog
from lunaris_runtime.schema import Course

from ..progress import LessonState, ObjectiveMark, newly_mastered_kcs
from .learning_event import LearningEvent, LearningEventType
from .store_protocol import IActivityStore

logger = structlog.get_logger()


def _lesson_label(course: Course, lesson_id: str) -> str | None:
    """The feed's lesson label: course-wide position + owning module title — the same
    "Lesson N" numbering the reader shows (lessons carry no title of their own)."""
    position = 0
    for module in course.modules:
        for lesson in module.lessons:
            position += 1
            if lesson.id == lesson_id:
                return f"Lesson {position} · {module.title}"
    return None


class LearningEventEmitter:
    """Turns progress writes into ``learning_events`` telemetry — strictly best-effort.

    Every method swallows ALL failures — event construction included, not just the store write —
    and logs them (with the bound request id + traceback), so a telemetry problem can never fail
    or delay the progress write it rides on. Emission fires only on REAL transitions: the reader
    re-marks in_progress on every open and re-marks understood idempotently, and the feed must
    record facts, not clicks.
    """

    def __init__(self, store: IActivityStore) -> None:
        self._store = store

    async def lesson_transition(
        self,
        *,
        user_id: str | None,
        course_id: str,
        course: Course | None,
        lesson_id: str,
        previous: LessonState | None,
        state: LessonState,
    ) -> None:
        """Emit ``started`` on first open (None → in_progress) or ``completed`` on the
        transition to done; anything else — including re-opens and re-completions — is silent."""
        try:
            if state == "in_progress" and previous is None:
                event_type: LearningEventType = "started"
            elif state == "done" and previous != "done":
                event_type = "completed"
            else:
                return
            event = LearningEvent(
                event_type=event_type,
                course_id=course_id,
                course_title=course.topic if course else None,
                lesson_id=lesson_id,
                lesson_title=_lesson_label(course, lesson_id) if course else None,
                kc_id=None,
                kc_label=None,
                occurred_at=datetime.now(UTC),
            )
            await self._store.record_event(user_id=user_id, event=event)
        except Exception:
            self._swallow(course_id)

    async def objective_understood(
        self,
        *,
        user_id: str | None,
        course_id: str,
        course: Course | None,
        objectives_before: list[ObjectiveMark] | None,
        module_id: str,
        objective_index: int,
    ) -> None:
        """Emit ``mastered`` for each KC this mark newly completes. Mastery is derivable only
        from the course payload + prior marks — when either is unavailable, nothing is emitted
        (facts are never guessed)."""
        try:
            if course is None or objectives_before is None:
                return
            labels = {node.id: node.label for node in course.graph.nodes}
            for kc_id in newly_mastered_kcs(course, objectives_before, module_id, objective_index):
                event = LearningEvent(
                    event_type="mastered",
                    course_id=course_id,
                    course_title=course.topic,
                    lesson_id=None,
                    lesson_title=None,
                    kc_id=kc_id,
                    kc_label=labels.get(kc_id),
                    occurred_at=datetime.now(UTC),
                )
                await self._store.record_event(user_id=user_id, event=event)
        except Exception:
            self._swallow(course_id)

    @staticmethod
    def _swallow(course_id: str) -> None:
        # Best-effort by contract: the progress write already succeeded; losing a telemetry row
        # is acceptable, failing the user's action is not. exc_info keeps a real outage and a
        # genuine emitter bug distinguishable in the logs.
        logger.warning("learning_event_write_failed", course_id=course_id, exc_info=True)
