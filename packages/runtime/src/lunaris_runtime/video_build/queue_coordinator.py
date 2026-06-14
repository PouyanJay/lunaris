import asyncio
from collections.abc import Mapping
from uuid import uuid4

import structlog
from pydantic import ValidationError

from ..persistence import IVideoJobQueue, IVideoStorage, PersistenceError, VideoArtifactPaths
from ..schema import VideoArtifact, VideoJob, VideoJobStatus, VideoKind
from .input_hash import video_input_hash

logger = structlog.get_logger()

# A job reaches one of these and stops; collect awaits the rest until then (or the timeout).
_TERMINAL = (VideoJobStatus.READY, VideoJobStatus.FAILED)

# How long finalize blocks on a single job before degrading it, and how often it re-polls. Generous
# by default (real renders are minutes; the in-proc worker drains during the build's own tail) — a
# safety bound, not the expected path; tests inject small values.
_DEFAULT_AWAIT_TIMEOUT_S = 900.0
_DEFAULT_POLL_S = 1.0


class QueueVideoBuildCoordinator:
    """Enqueues a build's lesson-video jobs onto the shared queue and awaits them at finalize — the
    in-proc (local) / cloud (V7) worker drains them.

    One instance per run, holding the build owner and the config snapshot stamped on every job, and
    deduping within the build so a lesson enqueues exactly once even when its module is re-verified
    across revise rounds. Enqueue is **best-effort**: a queue failure is logged and returns ``None``
    (that lesson simply gets no video) — a video must never break the course build (plan §0 failure
    policy). ``collect`` awaits the jobs with the same degrade-on-failure posture. The composition
    root builds this only when video is enabled, keyed, and owned, so its mere presence in run scope
    IS the gate.
    """

    def __init__(
        self,
        *,
        queue: IVideoJobQueue,
        storage: IVideoStorage,
        owner_id: str,
        config: Mapping[str, object] | None = None,
        await_timeout_s: float = _DEFAULT_AWAIT_TIMEOUT_S,
        poll_s: float = _DEFAULT_POLL_S,
    ) -> None:
        self._queue = queue
        self._storage = storage
        self._owner_id = owner_id
        self._config = dict(config or {})
        self._await_timeout_s = await_timeout_s
        self._poll_s = poll_s
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

    async def collect(self, jobs_by_lesson: Mapping[str, str]) -> dict[str, VideoArtifact]:
        # Await every job concurrently so the blocking wall-time is the slowest job, not the sum.
        # ``return_exceptions`` makes the degrade structural: even an unforeseen error from an await
        # becomes a FAILED artifact, so a video can NEVER abort the publish (plan §0 / AD-9).
        lesson_ids = list(jobs_by_lesson)
        results = await asyncio.gather(
            *(
                self._await_artifact(lesson_id, jobs_by_lesson[lesson_id])
                for lesson_id in lesson_ids
            ),
            return_exceptions=True,
        )
        artifacts: dict[str, VideoArtifact] = {}
        for lesson_id, result in zip(lesson_ids, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "video_build_collect_unexpected_error", lesson_id=lesson_id, exc_info=result
                )
                result = VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.FAILED)
            artifacts[lesson_id] = result
        return artifacts

    async def _await_artifact(self, lesson_id: str, job_id: str) -> VideoArtifact:
        job = await self._await_terminal(job_id)
        if job is not None and job.status is VideoJobStatus.READY:
            artifact = await self._download_artifact(job)
            if artifact is not None:
                return artifact
        # FAILED, unreadable, or still running past the timeout → the retry-state artifact. The
        # course publishes anyway; the lesson hero shows the regenerate menu (plan §0 policy).
        logger.info("video_build_lesson_degraded", job_id=job_id, lesson_id=lesson_id)
        return VideoArtifact(kind=VideoKind.LESSON, status=VideoJobStatus.FAILED)

    async def _await_terminal(self, job_id: str) -> VideoJob | None:
        """Poll the job until it settles READY/FAILED, returning it. ``None`` means "give up and
        degrade" — either the read failed or the job is still running past the timeout (the caller
        treats both the same: a FAILED retry-state artifact)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._await_timeout_s
        while True:
            try:
                job = await self._queue.get(job_id=job_id, owner_id=self._owner_id)
            except PersistenceError:
                logger.warning("video_build_collect_read_failed", job_id=job_id, exc_info=True)
                return None
            if job is None or job.status in _TERMINAL:
                return job
            if loop.time() >= deadline:
                logger.warning(
                    "video_build_collect_timeout", job_id=job_id, status=job.status.value
                )
                return None
            await asyncio.sleep(self._poll_s)

    async def _download_artifact(self, job: VideoJob) -> VideoArtifact | None:
        """The finished VideoArtifact the worker wrote at the source, or ``None`` if it is missing /
        malformed (then the caller degrades — never a half-stitched payload)."""
        path = VideoArtifactPaths.for_job(job).artifact
        try:
            return VideoArtifact.model_validate_json(await self._storage.download(path=path))
        except (PersistenceError, ValidationError):
            logger.warning("video_build_artifact_unreadable", job_id=job.id, exc_info=True)
            return None
