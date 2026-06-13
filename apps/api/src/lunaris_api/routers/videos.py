import hashlib
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from lunaris_runtime.persistence import VideoArtifactPaths
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind
from lunaris_runtime.schema.base import CourseModel

from ..config import Settings, get_settings
from ..dependencies import (
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
    """The wire shape of one video job: the row itself plus playback URLs once it is ready."""

    job: VideoJob
    video_url: str | None = None
    poster_url: str | None = None


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
) -> VideoJobView:
    """Enqueue one lesson-video job. The worker drains it; the job row is the status record."""
    job = VideoJob(
        id=uuid.uuid4().hex,
        user_id=owner_id,
        course_id=course_id,
        lesson_id=lesson_id,
        kind=VideoKind.LESSON,
        # V0: the inputs are the lesson coordinates only; V2 folds the lesson content + config in.
        input_hash=hashlib.sha256(f"{course_id}/{lesson_id}".encode()).hexdigest(),
    )
    await queue.enqueue(job)
    logger.info("video_job_enqueued", job_id=job.id, course_id=course_id, lesson_id=lesson_id)
    return VideoJobView(job=job)


@router.get(
    "/videos/{job_id}",
    dependencies=[Depends(require_video_generation_enabled)],
)
async def get_video_job(
    job_id: str,
    owner_id: CurrentUserIdDep,
    queue: VideoJobQueueDep,
    storage: VideoStorageDep,
) -> VideoJobView:
    """One job's status, owner-scoped; a READY job carries short-lived signed playback URLs.

    Deliberately NOT tier-gated (unlike enqueue): polling your own existing job consumes no
    generation capacity, and a user whose key was removed mid-flight must still see how their
    in-flight job ends. Owner scoping is the boundary that matters here.
    """
    job = await queue.get(job_id=job_id, owner_id=owner_id)
    if job is None:
        # 404 for missing AND not-owned alike — existence is never leaked across tenants.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video job not found")
    if job.status != VideoJobStatus.READY:
        return VideoJobView(job=job)
    paths = VideoArtifactPaths.for_job(job)
    return VideoJobView(
        job=job,
        video_url=await storage.signed_url(path=paths.mp4),
        poster_url=await storage.signed_url(path=paths.poster),
    )
