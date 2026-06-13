import asyncio

import structlog
from lunaris_runtime.persistence import ICourseStore
from lunaris_runtime.schema import Course, Lesson, Module, Segment, VideoJob

from lunaris_video._merrill import SEGMENT_ORDER
from lunaris_video.errors import VideoPipelineError
from lunaris_video.models import LessonSource
from lunaris_video.protocols import IGroundingPacketBuilder

_logger = structlog.get_logger(__name__)


class CourseStoreLessonSourceProvider:
    """Loads a job's lesson from the course store and flattens it into a ``LessonSource``.

    V1 grounded a video on the authored prose alone; V2 also hands the planner the lesson's
    verifier-PASSED claim packet (built behind ``IGroundingPacketBuilder``) — the only facts a
    scene may assert (cross-cutting principle 2). The prose stays for narrative framing.
    ``owner_id`` scopes the load to the job's owner — the Supabase store enforces it, the file
    store (single-user dev) ignores it.
    """

    def __init__(self, store: ICourseStore, *, packet_builder: IGroundingPacketBuilder) -> None:
        self._store = store
        self._packet_builder = packet_builder

    async def load(self, job: VideoJob) -> LessonSource:
        if job.lesson_id is None:
            raise VideoPipelineError("lesson video job has no lesson_id")
        course = await asyncio.to_thread(self._load_course, job)
        module, lesson = _find_lesson(course, job.lesson_id)
        prose = _lesson_prose(lesson)
        if not prose.strip():
            raise VideoPipelineError(f"lesson {job.lesson_id} has no prose to ground a video")
        packet = self._packet_builder.build_lesson_packet(course, lesson)
        _logger.info(
            "lesson_provider.loaded",
            lesson_id=lesson.id,
            prose_chars=len(prose),
            grounded_claims=len(packet.claims),
        )
        return LessonSource(
            course_topic=course.topic,
            lesson_title=module.competency or module.title,
            audience=course.scope_note or f"learners studying {course.topic}",
            prose=prose,
            packet=packet,
        )

    def _load_course(self, job: VideoJob) -> Course:
        try:
            return self._store.load(job.course_id, owner_id=job.user_id)
        except FileNotFoundError as exc:
            raise VideoPipelineError(f"course {job.course_id} not found for video job") from exc


def _find_lesson(course: Course, lesson_id: str) -> tuple[Module, Lesson]:
    for module in course.modules:
        for lesson in module.lessons:
            if lesson.id == lesson_id:
                return module, lesson
    raise VideoPipelineError(f"lesson {lesson_id} not found in course {course.id}")


def _lesson_prose(lesson: Lesson) -> str:
    segments: list[Segment] = [getattr(lesson.segments, name) for name in SEGMENT_ORDER]
    return "\n\n".join(segment.prose for segment in segments if segment.prose.strip())
