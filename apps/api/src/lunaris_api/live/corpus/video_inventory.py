import asyncio
import math
import re

import httpx
import structlog
from lunaris_live.corpus.video.bounded_inventory import bounded_inventory
from lunaris_live.corpus.video.extract_candidates import extract_candidates
from lunaris_live.corpus.video.models.verification_request import ClipVerificationRequest
from lunaris_live.corpus.video.protocols.media import IVideoMedia
from lunaris_live.corpus.video.schemas.inventory import VideoGap, VideoInventory
from lunaris_runtime.persistence.course_store_protocol import ICourseStore
from lunaris_runtime.persistence.persistence_error import PersistenceError
from lunaris_runtime.persistence.video_artifact_paths import VideoArtifactPaths
from lunaris_runtime.persistence.video_job_queue_protocol import IVideoJobQueue
from lunaris_runtime.persistence.video_storage_protocol import IVideoStorage
from lunaris_runtime.schema import Course, VideoJob, VideoJobStatus, VideoKind, VideoProvenance
from lunaris_runtime.video_build.input_hash import lesson_video_input_hash
from lunaris_video.assembly.outline_builder import build_video_outline
from lunaris_video.hashing.contract_hash import contract_hash
from lunaris_video.schemas import SceneContracts, TimingManifest
from pydantic import ValidationError

from .models.prepared_video_evidence import PreparedVideoEvidence
from .models.video_slot import VideoSlot
from .video_source import measured_video_source

logger = structlog.get_logger()
_MAX_VIDEOS = 10
# Bound cold-compile transfer: at most 20MB per movie and 200MB per course.
_MAX_MEDIA_BYTES = 20_000_000
_MAX_JSON_BYTES = 2_000_000


class StudioVideoInventory:
    """Owner-scoped ready jobs become generic candidates, never verified node mappings."""

    def __init__(
        self,
        courses: ICourseStore,
        queue: IVideoJobQueue,
        storage: IVideoStorage,
        media: IVideoMedia,
    ) -> None:
        self._courses, self._queue, self._storage, self._media = courses, queue, storage, media

    async def load(self, course_id: str, *, owner_id: str, run_id: str) -> VideoInventory:
        if not owner_id:
            raise FileNotFoundError(course_id)
        course = await asyncio.to_thread(self._courses.load, course_id, owner_id=owner_id)
        if course.id != course_id or course.status != "published":
            raise FileNotFoundError(course_id)
        jobs = await self._queue.list_for_course(course_id=course_id, owner_id=owner_id)
        slots = {
            (job.kind, job.lesson_id)
            for job in jobs
            if job.user_id == owner_id and job.course_id == course_id
        }
        clips, gaps = [], []
        if not slots:
            gaps.append(VideoGap(reason="no_ready_video"))
        if len(slots) > _MAX_VIDEOS:
            gaps.append(VideoGap(reason="inventory_limit"))
        for kind, lesson in sorted(slots, key=lambda item: (str(item[0]), item[1] or ""))[
            :_MAX_VIDEOS
        ]:
            result = await self._slot(course, VideoSlot(owner_id, kind, lesson))
            clips.extend(result.clips)
            gaps.extend(result.gaps)
        logger.info(
            "live.corpus.video_inventory",
            run_id=run_id,
            course_id=course_id,
            clip_count=len(clips),
            gap_count=len(gaps),
        )
        return bounded_inventory(clips, gaps)

    async def verify(self, request: ClipVerificationRequest) -> bool:
        course_id, clip = request.course_id, request.clip
        owner_id, run_id = request.owner_id, request.run_id
        if not owner_id:
            return False
        try:
            course = await asyncio.to_thread(self._courses.load, course_id, owner_id=owner_id)
        except FileNotFoundError:
            return False
        if course.id != course_id or course.status != "published":
            return False
        job = await self._queue.get(job_id=clip.job_id, owner_id=owner_id)
        if not _owned_ready_job(job, course_id, owner_id, clip.job_id):
            return False
        assert job is not None
        slot = VideoSlot(owner_id, job.kind, job.lesson_id)
        if await self._latest(course.id, slot) != job:
            return False
        inventory = await self._slot(course, slot, expected=job)
        if clip not in inventory.clips:
            return False
        verified = await self._latest(course.id, slot) == job
        logger.info(
            "live.corpus.clip_revalidated",
            run_id=run_id,
            course_id=course_id,
            job_id=clip.job_id,
            verified=verified,
        )
        return verified

    async def _latest(self, course_id: str, slot: VideoSlot) -> VideoJob | None:
        return await self._queue.find_latest_ready(
            course_id=course_id, lesson_id=slot.lesson_id, kind=slot.kind, owner_id=slot.owner_id
        )

    async def _slot(
        self, course: Course, slot: VideoSlot, *, expected: VideoJob | None = None
    ) -> VideoInventory:
        job = await self._queue.find_latest_ready(
            course_id=course.id, lesson_id=slot.lesson_id, kind=slot.kind, owner_id=slot.owner_id
        )
        if (
            job is None
            or (expected is not None and job != expected)
            or job.user_id != slot.owner_id
            or job.course_id != course.id
            or job.status != VideoJobStatus.READY
            or job.kind != slot.kind
            or job.lesson_id != slot.lesson_id
        ):
            return VideoInventory(gaps=(VideoGap(reason="no_ready_video"),))
        try:
            async with asyncio.timeout(40):
                return await self._one(course, job)
        except (
            PersistenceError,
            ValidationError,
            ValueError,
            KeyError,
            TimeoutError,
            httpx.HTTPError,
        ):
            return _gap(job, "unavailable")

    async def _one(self, course: Course, job: VideoJob) -> VideoInventory:
        if _stale(course, job):
            return _gap(job, "stale")
        if not all(
            re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value)
            for value in (job.user_id, job.course_id, job.id)
        ):
            return _gap(job, "unavailable")
        paths = VideoArtifactPaths.for_job(job)
        raw_contracts, raw_timing, raw_provenance = await asyncio.gather(
            *(self._json(path) for path in (paths.contracts, paths.timing, paths.provenance))
        )
        try:
            contracts = SceneContracts.model_validate_json(raw_contracts)
            timing = TimingManifest.model_validate_json(raw_timing)
            provenance = VideoProvenance.model_validate_json(raw_provenance)
            if (
                provenance.job_id != job.id
                or provenance.course_id != job.course_id
                or provenance.input_hash != job.input_hash
                or provenance.contract_hash != job.contract_hash
                or contract_hash(contracts) != job.contract_hash
            ):
                return _gap(job, "stale")
            if provenance.degraded_scenes or provenance.narration_dropped_for_desync:
                return _gap(job, "degraded")
            _validate_timing(contracts, timing)
            outline = build_video_outline(contracts, timing)
        except (ValidationError, KeyError, ValueError):
            return _gap(job, "malformed_timing")
        if not outline.transcript:
            return _gap(job, "silent")
        evidence = PreparedVideoEvidence(
            job_id=job.id,
            media_path=paths.mp4,
            title=contracts.topic,
            outline=outline,
            artifact_bytes=(raw_contracts, raw_timing, raw_provenance),
        )
        return await self._candidates(evidence)

    async def _candidates(self, evidence: PreparedVideoEvidence) -> VideoInventory:
        try:
            media = await self._media.inspect(path=evidence.media_path, max_bytes=_MAX_MEDIA_BYTES)
        except (ValueError, httpx.HTTPError, TimeoutError):
            return VideoInventory(
                gaps=(VideoGap(job_id=evidence.job_id, reason="media_unverified"),)
            )
        try:
            source = measured_video_source(evidence, media)
        except ValidationError:
            return VideoInventory(
                gaps=(VideoGap(job_id=evidence.job_id, reason="malformed_timing"),)
            )
        return extract_candidates(source)

    async def _json(self, path: str) -> bytes:
        content = await self._storage.download(path=path)
        if len(content) > _MAX_JSON_BYTES:
            raise ValueError("video metadata exceeds budget")
        return content


def _gap(job: VideoJob, reason: str) -> VideoInventory:
    return VideoInventory(gaps=(VideoGap(job_id=job.id, reason=reason),))


def _owned_ready_job(job: VideoJob | None, course_id: str, owner_id: str, job_id: str) -> bool:
    return (
        job is not None
        and job.id == job_id
        and job.user_id == owner_id
        and job.course_id == course_id
        and job.status == VideoJobStatus.READY
    )


def _stale(course: Course, job: VideoJob) -> bool:
    if job.kind != VideoKind.LESSON:
        # Course-level producers do not fingerprint course content yet.
        return True
    lesson = next(
        (
            lesson
            for module in course.modules
            for lesson in module.lessons
            if lesson.id == job.lesson_id
        ),
        None,
    )
    target = job.config.get("target_seconds")
    if lesson is None or not isinstance(target, int) or isinstance(target, bool):
        return True
    return lesson_video_input_hash(job.course_id, lesson, target_seconds=target) != job.input_hash


def _validate_timing(contracts: SceneContracts, timing: TimingManifest) -> None:
    if set(timing.root) != {scene.id for scene in contracts.scenes}:
        raise ValueError("timing scene mismatch")
    for scene in contracts.scenes:
        timed = timing[scene.id]
        if len({beat.id for beat in timed.beats}) != len(timed.beats) or {
            beat.id for beat in timed.beats
        } != {beat.id for beat in scene.beats}:
            raise ValueError("timing beat mismatch")
        if not math.isfinite(timed.total_s) or timed.total_s <= 0:
            raise ValueError("invalid scene duration")
        for beat in timed.beats:
            if (
                not math.isfinite(beat.anim_s)
                or beat.anim_s <= 0
                or not math.isfinite(beat.audio_s)
                or beat.audio_s < 0
                or beat.audio_s > beat.anim_s
                or (beat.audio and beat.estimated)
            ):
                raise ValueError("unmeasured or invalid beat timing")
        if not math.isclose(sum(beat.anim_s for beat in timed.beats), timed.total_s, abs_tol=0.001):
            raise ValueError("scene duration disagrees with beats")
