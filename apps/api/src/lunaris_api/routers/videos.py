import asyncio
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from lunaris_runtime.logging import bind_request_id
from lunaris_runtime.persistence import (
    ICourseStore,
    IVideoStorage,
    PersistenceError,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind, VideoProvenance
from lunaris_runtime.schema.base import CourseModel
from lunaris_runtime.video_build import video_input_hash
from lunaris_video.schemas import TimingManifest
from pydantic import ValidationError

from ..config import Settings, get_settings
from ..dependencies import (
    CourseStoreDep,
    CredentialVaultDep,
    CurrentUserIdDep,
    VideoJobQueueDep,
    VideoStorageDep,
    explain_is_available,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api", tags=["videos"])

_KEYLESS_DETAIL = (
    "Video generation needs an Anthropic API key — add one in Settings. "
    "The Draft tier does not include videos."
)


class VideoJobView(CourseModel):
    """The wire shape of one video job: the row itself, playback URLs, a captions URL (narrated
    videos only) and the grounding provenance once it is ready."""

    job: VideoJob
    video_url: str | None = None
    poster_url: str | None = None
    captions_url: str | None = None
    provenance: VideoProvenance | None = None


def require_video_generation_enabled(
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """The operator kill-switch: with ``VIDEO_GENERATION_ENABLED`` off the surface does not
    exist — 404, not 403, so a prod promote mid-workstream exposes nothing probeable."""
    if not settings.video_generation_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Video generation is not enabled"
        )


async def require_keyed_caller(owner_id: CurrentUserIdDep, vault: CredentialVaultDep) -> str:
    """The keyed-only tier gate: videos are not a Draft-tier capability (plan §0).

    Mirrors the build/explain credential ladder: with a vault (auth + BYOK) the caller's own
    Anthropic key decides; without one, the process env does (single-user / auth-off deployments).
    """
    if vault is not None:
        keyed = bool(await vault.reveal(user_id=owner_id, provider="anthropic"))
    else:
        keyed = explain_is_available()
    if not keyed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_KEYLESS_DETAIL)
    return owner_id


@router.post(
    "/courses/{course_id}/lessons/{lesson_id}/video",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_video_generation_enabled)],
)
async def enqueue_lesson_video(
    course_id: str,
    lesson_id: str,
    owner_id: Annotated[str, Depends(require_keyed_caller)],
    queue: VideoJobQueueDep,
    store: CourseStoreDep,
    response: Response,
) -> VideoJobView:
    """Enqueue one lesson-video job. The worker drains it; the job row is the status record.

    Two guards before enqueue (V4-T0, the V0-deferred safety): the caller must **own** the course
    and the lesson must exist in it (else 404 — never spend worker capacity on a course you don't
    own), and a **duplicate** is deduped — a video already queued/in-flight for this lesson is
    returned rather than re-enqueued as a twin (idempotent Generate)."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    await _assert_owns_lesson(store, course_id=course_id, lesson_id=lesson_id, owner_id=owner_id)
    existing = await queue.find_active(
        course_id=course_id, lesson_id=lesson_id, kind=VideoKind.LESSON, owner_id=owner_id
    )
    if existing is not None:
        logger.info(
            "video_job_enqueue_deduped",
            job_id=existing.id,
            course_id=course_id,
            lesson_id=lesson_id,
        )
        return VideoJobView(job=existing)
    job = VideoJob(
        id=uuid.uuid4().hex,
        user_id=owner_id,
        course_id=course_id,
        lesson_id=lesson_id,
        kind=VideoKind.LESSON,
        input_hash=video_input_hash(course_id, lesson_id),
    )
    await queue.enqueue(job)
    logger.info("video_job_enqueued", job_id=job.id, course_id=course_id, lesson_id=lesson_id)
    return VideoJobView(job=job)


async def _assert_owns_lesson(
    store: ICourseStore, *, course_id: str, lesson_id: str, owner_id: str
) -> None:
    """404 unless the caller owns ``course_id`` AND it contains ``lesson_id``.

    ``load`` is owner-scoped and raises ``FileNotFoundError`` for a missing OR not-owned course, so
    a not-found answer never leaks another tenant's course. The load is synchronous (file / blocking
    supabase-py) — off-loaded so the event loop isn't blocked."""
    try:
        course = await asyncio.to_thread(lambda: store.load(course_id, owner_id=owner_id))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        ) from exc
    if not any(lesson.id == lesson_id for module in course.modules for lesson in module.lessons):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")


@router.get(
    "/videos/{job_id}",
    dependencies=[Depends(require_video_generation_enabled)],
)
async def get_video_job(
    job_id: str,
    owner_id: CurrentUserIdDep,
    queue: VideoJobQueueDep,
    storage: VideoStorageDep,
    response: Response,
) -> VideoJobView:
    """One job's status, owner-scoped; a READY job carries short-lived signed playback URLs.

    Deliberately NOT tier-gated (unlike enqueue): polling your own existing job consumes no
    generation capacity, and a user whose key was removed mid-flight must still see how their
    in-flight job ends. Owner scoping is the boundary that matters here.
    """
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    job = await queue.get(job_id=job_id, owner_id=owner_id)
    if job is None:
        # 404 for missing AND not-owned alike — existence is never leaked across tenants.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video job not found")
    if job.status != VideoJobStatus.READY:
        return VideoJobView(job=job)
    paths = VideoArtifactPaths.for_job(job)
    # The four reads are independent — gather them so a READY status poll is one round-trip's worth
    # of latency, not four sequential ones.
    video_url, poster_url, captions_url, provenance = await asyncio.gather(
        storage.signed_url(path=paths.mp4),
        storage.signed_url(path=paths.poster),
        _captions_url_if_narrated(storage, paths),
        _read_provenance(storage, paths.provenance),
    )
    return VideoJobView(
        job=job,
        video_url=video_url,
        poster_url=poster_url,
        captions_url=captions_url,
        provenance=provenance,
    )


async def _read_provenance(storage: IVideoStorage, path: str) -> VideoProvenance | None:
    """The video's grounding provenance, threaded onto the wire. Supplementary to playback, so a
    missing or malformed artifact (e.g. a job rendered before V2) degrades to None, never a 500."""
    try:
        return VideoProvenance.model_validate_json(await storage.download(path=path))
    except (PersistenceError, ValidationError) as exc:
        # reason distinguishes the expected case (a pre-V2 job has no artifact) from schema drift.
        logger.warning("video_provenance_unavailable", path=path, reason=type(exc).__name__)
        return None


async def _captions_url_if_narrated(
    storage: IVideoStorage, paths: VideoArtifactPaths
) -> str | None:
    """A signed captions URL — but ONLY for a narrated video, so the player never attaches a track
    that 404s. The timing manifest (always present for a READY job) is the source of truth for
    narrated-ness; a silent or pre-V3 job is voiceless and gets no captions URL."""
    try:
        manifest = TimingManifest.model_validate_json(await storage.download(path=paths.timing))
    except (PersistenceError, ValidationError) as exc:
        logger.warning("video_timing_unavailable", path=paths.timing, reason=type(exc).__name__)
        return None
    if not manifest.is_voiced:
        return None
    return await storage.signed_url(path=paths.captions)
