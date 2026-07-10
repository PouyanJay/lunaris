import asyncio
import hashlib
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Response, status
from lunaris_runtime.logging import bind_request_id
from lunaris_runtime.persistence import (
    CoverArtifactPaths,
    ICourseStore,
    ICoverStorage,
    PersistenceError,
)
from lunaris_runtime.schema import (
    Course,
    CoverJob,
    CoverJobStatus,
    CoverProvenance,
    CoverStylePreset,
)
from lunaris_runtime.schema.base import CourseModel
from pydantic import ValidationError

from ..dependencies import (
    CourseStoreDep,
    CoverJobQueueDep,
    CoverStorageDep,
    CurrentUserIdDep,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api", tags=["covers"])


class CoverJobView(CourseModel):
    """The wire shape of one cover job: the row itself, a short-lived signed image URL once the
    cover is READY, and the structural provenance (the anti-slop record — which models drew and
    inspected it). A non-READY job carries just the row so the reader can render its progress."""

    job: CoverJob
    image_url: str | None = None
    provenance: CoverProvenance | None = None


def _cover_input_hash(course: Course, style_preset: CoverStylePreset) -> str:
    """Fingerprint the cover's generation inputs — the course topic + the chosen art-direction
    preset — so a later staleness check can flag a cover outdated when the topic changes."""
    digest = hashlib.sha256()
    digest.update(course.id.encode())
    digest.update(b"\x00")
    digest.update(course.topic.encode())
    digest.update(b"\x00")
    digest.update(style_preset.value.encode())
    return digest.hexdigest()


async def _load_owned_course(store: ICourseStore, *, course_id: str, owner_id: str) -> Course:
    """The course if the caller owns it, else 404. ``load`` is owner-scoped and raises
    ``FileNotFoundError`` for a missing OR not-owned course (existence never leaks across tenants);
    it's synchronous (file / blocking supabase-py), so it's off-loaded to keep the loop free."""
    try:
        return await asyncio.to_thread(lambda: store.load(course_id, owner_id=owner_id))
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        ) from None


@router.post("/courses/{course_id}/cover", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_cover(
    course_id: str,
    owner_id: CurrentUserIdDep,
    queue: CoverJobQueueDep,
    store: CourseStoreDep,
    response: Response,
) -> CoverJobView:
    """Enqueue one course cover-image job. The worker drains it; the job row is the status record.

    The caller must **own** the course (else 404 — never spend worker capacity on a course you don't
    own), and a **duplicate** is deduped (idempotent). One cover per course, so the dedup keys on
    (course, owner) with no kind/lesson dimension. (The OpenAI-key tier gate lands in T3; the
    walking-skeleton stub producer needs no key.)"""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    course = await _load_owned_course(store, course_id=course_id, owner_id=owner_id)
    existing = await queue.find_active(course_id=course_id, owner_id=owner_id)
    if existing is not None:
        logger.info("cover_job_enqueue_deduped", job_id=existing.id, course_id=course_id)
        return CoverJobView(job=existing)
    style_preset = CoverStylePreset.NOCTURNE
    job = CoverJob(
        id=uuid.uuid4().hex,
        user_id=owner_id,
        course_id=course_id,
        style_preset=style_preset,
        input_hash=_cover_input_hash(course, style_preset),
    )
    await queue.enqueue(job)
    logger.info("cover_job_enqueued", job_id=job.id, course_id=course_id)
    return CoverJobView(job=job)


@router.get("/covers/{job_id}")
async def get_cover_job(
    job_id: str,
    owner_id: CurrentUserIdDep,
    queue: CoverJobQueueDep,
    storage: CoverStorageDep,
    response: Response,
) -> CoverJobView:
    """One cover job's status, owner-scoped; a READY job carries a short-lived signed image URL and
    the structural provenance.

    Deliberately NOT tier-gated (unlike enqueue): polling your own existing job consumes no
    generation capacity. Owner scoping is the boundary that matters here."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    job = await queue.get(job_id=job_id, owner_id=owner_id)
    if job is None:
        # 404 for missing AND not-owned alike — existence is never leaked across tenants.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover job not found")
    if job.status != CoverJobStatus.READY:
        return CoverJobView(job=job)
    paths = CoverArtifactPaths.for_job(job)
    image_url, provenance = await asyncio.gather(
        storage.signed_url(path=paths.image),
        _read_provenance(storage, paths.provenance),
    )
    return CoverJobView(job=job, image_url=image_url, provenance=provenance)


async def _read_provenance(storage: ICoverStorage, path: str) -> CoverProvenance | None:
    """The cover's structural provenance, threaded onto the wire. Supplementary to display, so a
    missing or malformed artifact degrades to None, never a 500."""
    try:
        return CoverProvenance.model_validate_json(await storage.download(path=path))
    except (PersistenceError, ValidationError) as exc:
        logger.warning("cover_provenance_unavailable", path=path, reason=type(exc).__name__)
        return None
