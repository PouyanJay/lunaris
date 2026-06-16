import asyncio

import structlog
from lunaris_runtime.persistence import (
    ICourseStore,
    IVideoStorage,
    PersistenceError,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import Course, Lesson, Module, Segment, VideoJob, VideoJobStatus
from pydantic import ValidationError

from lunaris_video._merrill import SEGMENT_ORDER
from lunaris_video.errors import VideoPipelineError
from lunaris_video.models import LessonSource, SiblingContractDigest
from lunaris_video.planning import digest_of, project_video_dependencies
from lunaris_video.protocols import IGroundingPacketBuilder
from lunaris_video.schemas import SceneContracts

_logger = structlog.get_logger(__name__)


class CourseStoreLessonSourceProvider:
    """Loads a job's lesson from the course store and flattens it into a ``LessonSource``.

    V1 grounded a video on the authored prose alone; V2 also hands the planner the lesson's
    verifier-PASSED claim packet (built behind ``IGroundingPacketBuilder``) — the only facts a
    scene may assert (cross-cutting principle 2). The prose stays for narrative framing.
    ``owner_id`` scopes the load to the job's owner — the Supabase store enforces it, the file
    store (single-user dev) ignores it.
    """

    def __init__(
        self,
        store: ICourseStore,
        *,
        packet_builder: IGroundingPacketBuilder,
        video_storage: IVideoStorage | None = None,
    ) -> None:
        self._store = store
        self._packet_builder = packet_builder
        # When present, the planner is given digests of the upstream sibling videos this lesson
        # depends on (its prerequisites in the course's video DAG). None on the no-fetch path —
        # the source is then framing-only as before.
        self._video_storage = video_storage

    async def load(self, job: VideoJob) -> LessonSource:
        if job.lesson_id is None:
            raise VideoPipelineError("lesson video job has no lesson_id")
        course = await asyncio.to_thread(self._load_course, job)
        module, lesson = _find_lesson(course, job.lesson_id)
        prose = _lesson_prose(lesson)
        if not prose.strip():
            raise VideoPipelineError(f"lesson {job.lesson_id} has no prose to ground a video")
        packet = self._packet_builder.build_lesson_packet(course, lesson)
        upstream = await self._upstream_digests(job, course)
        _logger.info(
            "lesson_provider.loaded",
            lesson_id=lesson.id,
            prose_chars=len(prose),
            grounded_claims=len(packet.claims),
            upstream_siblings=len(upstream),
        )
        return LessonSource(
            course_topic=course.topic,
            lesson_title=module.competency or module.title,
            audience=course.scope_note or f"learners studying {course.topic}",
            prose=prose,
            packet=packet,
            upstream_siblings=upstream,
        )

    async def _upstream_digests(
        self, job: VideoJob, course: Course
    ) -> tuple[SiblingContractDigest, ...]:
        """Digest each upstream sibling video this lesson depends on — best-effort, in topo order.

        The video DAG (projected from ``Course.graph``) names the upstream lessons; each one's built
        contract is fetched from storage and digested. A skip (no store, not yet built, contract
        gone, schema drift) drops just that one — never fails the load — so a lesson always plans.
        """
        if self._video_storage is None or job.lesson_id is None:
            return ()
        upstream_ids = project_video_dependencies(course).upstream_of(job.lesson_id)
        digests: list[SiblingContractDigest] = []
        for lesson_id in upstream_ids:
            digest = await self._upstream_digest(job, course, lesson_id)
            if digest is not None:
                digests.append(digest)
        return tuple(digests)

    async def _upstream_digest(
        self, job: VideoJob, course: Course, lesson_id: str
    ) -> SiblingContractDigest | None:
        assert self._video_storage is not None  # guarded by _upstream_digests
        module, lesson = _find_lesson(course, lesson_id)
        artifact = lesson.video
        if (
            artifact is None
            or artifact.status is not VideoJobStatus.READY
            or artifact.job_id is None
        ):
            return None  # the upstream has not been built yet — nothing to digest
        path = VideoArtifactPaths.for_coordinates(
            job.user_id, job.course_id, artifact.job_id
        ).contracts
        try:
            data = await self._video_storage.download(path=path)
        except PersistenceError:
            _logger.warning(
                "upstream_contract_unavailable", upstream_lesson_id=lesson_id, path=path
            )
            return None
        try:
            contract = SceneContracts.model_validate_json(data)
        except ValidationError:
            _logger.warning(
                "upstream_contract_unparseable", upstream_lesson_id=lesson_id, path=path
            )
            return None
        return digest_of(module.competency or module.title, contract)

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
