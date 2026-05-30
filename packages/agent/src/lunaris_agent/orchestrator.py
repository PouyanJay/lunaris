import structlog
from lunaris_runtime.logging import bind_run_id
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import Course, CourseStatus

from .models.router import ModelRouter

logger = structlog.get_logger()


class Orchestrator:
    """Owns the plan and the course-object; delegates the work.

    Stage 0 is the walking skeleton: it proves the layers talk (schema → persistence
    → logging) and that a correlation id flows through every line. Real subagents and
    the deep-agents harness wire in from Stage 1, where a live model is first needed.
    """

    def __init__(self, store: CourseStore, router: ModelRouter | None = None) -> None:
        self._store = store
        self._router = router

    async def run(self, topic: str, *, course_id: str, run_id: str) -> Course:
        bind_run_id(run_id)
        logger.info("course_run_started", topic=topic, course_id=course_id)

        course = Course(id=course_id, topic=topic)
        # Walking-skeleton stub step: advance one status and persist — "I am alive".
        course.status = CourseStatus.MAPPING
        self._store.save(course)

        logger.info("course_run_completed", course_id=course_id, status=course.status.value)
        return course
