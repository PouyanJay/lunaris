import structlog
from lunaris_runtime.schema import CourseBrief, Module, VideoJob, VideoKind

from lunaris_video.errors import VideoPipelineError
from lunaris_video.models import GroundingPacket, LessonSource
from lunaris_video.protocols import IGroundingPacketBuilder

_logger = structlog.get_logger(__name__)


class CourseVideoSourceProvider:
    """Resolves a course-level (SUMMARY/OVERVIEW) job into the source the pipeline plans from.

    Unlike the lesson provider, this never loads the course store: the build enqueues these jobs
    before the course is persisted (it saves only at finalize), so the harness snapshots grounding
    onto ``job.config["grounding"]`` at enqueue (AD-1). Here that snapshot is reconstituted into the
    typed runtime models (``Module`` list for the trailer, ``CourseBrief`` for the intro) and handed
    to the same ``IGroundingPacketBuilder`` the lesson path uses — so a course video grounds in the
    designed curriculum / researched standard, never in anything the moat didn't support.
    """

    def __init__(self, *, packet_builder: IGroundingPacketBuilder) -> None:
        self._packet_builder = packet_builder

    async def load(self, job: VideoJob) -> LessonSource:
        grounding = self._grounding(job)
        if job.kind is VideoKind.SUMMARY:
            return self._summary_source(grounding)
        if job.kind is VideoKind.OVERVIEW:
            return self._overview_source(grounding)
        raise VideoPipelineError(f"course-video provider cannot serve kind {job.kind.value}")

    def _summary_source(self, grounding: dict[str, object]) -> LessonSource:
        topic = str(grounding.get("topic") or "")
        modules = [Module.model_validate(raw) for raw in _as_list(grounding.get("modules"))]
        packet = self._packet_builder.build_summary_packet(topic=topic, modules=modules)
        titles = ", ".join(module.title for module in modules)
        prose = (
            f"A short trailer for the course “{topic or 'this course'}”, walking through its "
            f"{len(modules)} modules: {titles}."
        )
        return self._source(topic, f"Course trailer: {topic}", topic, prose, packet)

    def _overview_source(self, grounding: dict[str, object]) -> LessonSource:
        brief = CourseBrief.model_validate(_as_dict(grounding.get("brief")))
        packet = self._packet_builder.build_overview_packet(brief)
        subject = brief.subject or "this topic"
        prose = (
            f"An introduction to {subject}: {brief.goal or 'what it is and why it matters'}. "
            "What the topic is, why it matters, and where this course takes you."
        )
        return self._source(subject, f"Course overview: {subject}", brief.audience, prose, packet)

    @staticmethod
    def _source(
        topic: str, title: str, audience: str, prose: str, packet: GroundingPacket
    ) -> LessonSource:
        # LessonSource forbids blank fields (a blank surfaces later as a hallucinated prompt block),
        # so a thin snapshot degrades to honest defaults rather than failing construction.
        return LessonSource(
            course_topic=topic or "this course",
            lesson_title=title.strip() or "Course video",
            audience=audience.strip() or f"learners exploring {topic or 'this course'}",
            prose=prose,
            packet=packet,
        )

    def _grounding(self, job: VideoJob) -> dict[str, object]:
        grounding = job.config.get("grounding")
        if not isinstance(grounding, dict):
            raise VideoPipelineError(
                f"course-video job {job.id} has no grounding snapshot in its config"
            )
        _logger.info("course_video_grounding_resolved", job_id=job.id, kind=job.kind.value)
        return grounding


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
