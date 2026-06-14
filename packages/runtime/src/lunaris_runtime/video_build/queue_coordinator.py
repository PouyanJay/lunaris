from collections.abc import Mapping
from uuid import uuid4

import structlog

from ..persistence import IVideoJobQueue, PersistenceError
from ..schema import VideoJob, VideoKind
from .input_hash import video_input_hash

logger = structlog.get_logger()


class QueueVideoBuildCoordinator:
    """Enqueues a build's lesson-video jobs onto the shared queue — the in-proc (local) / cloud (V7)
    worker drains them.

    One instance per run, holding the build owner and the config snapshot stamped on every job, and
    deduping within the build so a lesson enqueues exactly once even when its module is re-verified
    across revise rounds. Enqueue is **best-effort**: a queue failure is logged and returns ``None``
    (that lesson simply gets no video) — a video must never break the course build (plan §0 failure
    policy). The composition root builds this only when video is enabled, keyed, and owned, so its
    mere presence in run scope IS the gate.
    """

    def __init__(
        self,
        *,
        queue: IVideoJobQueue,
        owner_id: str,
        config: Mapping[str, object] | None = None,
    ) -> None:
        self._queue = queue
        self._owner_id = owner_id
        self._config = dict(config or {})
        self._enqueued: dict[str, str] = {}  # lesson_id → job_id (per-build dedup)

    async def enqueue_lesson(self, *, course_id: str, lesson_id: str) -> str | None:
        existing = self._enqueued.get(lesson_id)
        if existing is not None:
            return existing  # one job per lesson per build (a re-verified clean module re-enters)
        job = VideoJob(
            id=uuid4().hex,
            user_id=self._owner_id,
            course_id=course_id,
            lesson_id=lesson_id,
            kind=VideoKind.LESSON,
            input_hash=video_input_hash(course_id, lesson_id),
            config=dict(self._config),
        )
        try:
            await self._queue.enqueue(job)
        except PersistenceError:
            # The production queue is @guard-ed, so every backend failure arrives as a
            # PersistenceError; swallow it (best-effort) so a queue hiccup degrades to "no video"
            # for that lesson, never a dead build.
            logger.warning(
                "video_build_enqueue_failed",
                course_id=course_id,
                lesson_id=lesson_id,
                exc_info=True,
            )
            return None
        self._enqueued[lesson_id] = job.id
        logger.info(
            "video_build_lesson_enqueued", job_id=job.id, course_id=course_id, lesson_id=lesson_id
        )
        return job.id
