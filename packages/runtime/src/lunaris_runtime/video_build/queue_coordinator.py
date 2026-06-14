import asyncio
from collections.abc import Mapping, Sequence
from uuid import uuid4

import structlog
from pydantic import ValidationError

from ..persistence import IVideoJobQueue, IVideoStorage, PersistenceError, VideoArtifactPaths
from ..schema import CourseBrief, Module, VideoArtifact, VideoJob, VideoJobStatus, VideoKind
from .input_hash import video_input_hash
from .video_lengths import target_seconds_for

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
        self._enqueued_course: dict[VideoKind, str] = {}  # summary/overview → job_id (per build)

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

    async def enqueue_summary(
        self, *, course_id: str, topic: str, modules: Sequence[Module]
    ) -> str | None:
        # The trailer grounds in the designed curriculum; snapshot topic + the modules (without the
        # not-yet-authored lessons) onto the job so the worker grounds it without the unpersisted
        # course (AD-1). model_dump(mode="json") keeps the config JSON-serialisable for the queue.
        grounding = {
            "topic": topic,
            "modules": [module.model_dump(mode="json") for module in modules],
        }
        return await self._enqueue_course_video(VideoKind.SUMMARY, course_id, grounding)

    async def enqueue_overview(self, *, course_id: str, brief: CourseBrief) -> str | None:
        # The intro grounds in the brief + researched standard; snapshot the whole brief (it carries
        # ``research`` once the research stage ran) onto the job — same AD-1 rationale as summary.
        grounding = {"brief": brief.model_dump(mode="json")}
        return await self._enqueue_course_video(VideoKind.OVERVIEW, course_id, grounding)

    async def _enqueue_course_video(
        self, kind: VideoKind, course_id: str, grounding: dict[str, object]
    ) -> str | None:
        existing = self._enqueued_course.get(kind)
        if existing is not None:
            return existing  # one summary + one overview per build
        config = dict(self._config)
        config["target_seconds"] = target_seconds_for(kind)
        config["grounding"] = grounding
        job = VideoJob(
            id=uuid4().hex,
            user_id=self._owner_id,
            course_id=course_id,
            lesson_id=None,  # course-level kinds carry no lesson
            kind=kind,
            input_hash=video_input_hash(course_id, kind.value),
            config=config,
        )
        try:
            await self._queue.enqueue(job)
        except PersistenceError:
            # Best-effort, like enqueue_lesson: a queue hiccup degrades to "no course video",
            # never a dead build.
            logger.warning(
                "video_build_course_enqueue_failed",
                course_id=course_id,
                kind=kind.value,
                exc_info=True,
            )
            return None
        self._enqueued_course[kind] = job.id
        logger.info(
            "video_build_course_enqueued", job_id=job.id, course_id=course_id, kind=kind.value
        )
        return job.id

    async def collect(self, jobs_by_lesson: Mapping[str, str]) -> dict[str, VideoArtifact]:
        return await self._collect(jobs_by_lesson, degraded_kind=VideoKind.LESSON)

    async def collect_course_videos(
        self, jobs_by_kind: Mapping[VideoKind, str]
    ) -> dict[VideoKind, VideoArtifact]:
        # Each course-level job degrades to ITS OWN kind, so the reader's Overview section shows the
        # right retry state per slot — hence collect keys by kind and uses it as the degrade kind.
        results = await asyncio.gather(
            *(
                self._await_artifact(job_id, degraded_kind=kind)
                for kind, job_id in jobs_by_kind.items()
            ),
            return_exceptions=True,
        )
        artifacts: dict[VideoKind, VideoArtifact] = {}
        for kind, result in zip(jobs_by_kind, results, strict=True):
            artifacts[kind] = self._degrade_on_error(result, degraded_kind=kind)
        return artifacts

    async def _collect(
        self, jobs_by_key: Mapping[str, str], *, degraded_kind: VideoKind
    ) -> dict[str, VideoArtifact]:
        # Await every job concurrently so the blocking wall-time is the slowest job, not the sum.
        # ``return_exceptions`` makes the degrade structural: even an unforeseen error from an await
        # becomes a FAILED artifact, so a video can NEVER abort the publish (plan §0 / AD-9).
        keys = list(jobs_by_key)
        results = await asyncio.gather(
            *(self._await_artifact(jobs_by_key[key], degraded_kind=degraded_kind) for key in keys),
            return_exceptions=True,
        )
        return {
            key: self._degrade_on_error(result, degraded_kind=degraded_kind)
            for key, result in zip(keys, results, strict=True)
        }

    @staticmethod
    def _degrade_on_error(
        result: VideoArtifact | BaseException, *, degraded_kind: VideoKind
    ) -> VideoArtifact:
        if isinstance(result, BaseException):
            logger.warning(
                "video_build_collect_unexpected_error", kind=degraded_kind.value, exc_info=result
            )
            return VideoArtifact(kind=degraded_kind, status=VideoJobStatus.FAILED)
        return result

    async def _await_artifact(self, job_id: str, *, degraded_kind: VideoKind) -> VideoArtifact:
        job = await self._await_terminal(job_id)
        if job is not None and job.status is VideoJobStatus.READY:
            artifact = await self._download_artifact(job)
            if artifact is not None:
                return artifact
        # FAILED, unreadable, or still running past the timeout → the retry-state artifact (carrying
        # the right kind). The course publishes anyway; the hero shows the regenerate menu (§0).
        logger.info("video_build_degraded", job_id=job_id, kind=degraded_kind.value)
        return VideoArtifact(kind=degraded_kind, status=VideoJobStatus.FAILED)

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
