import asyncio
import os
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
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

from ..cover_display_transform import COVER_DISPLAY_TRANSFORM
from ..cover_enqueue import enqueue_cover_job
from ..dependencies import (
    CourseStoreDep,
    CoverJobQueueDep,
    CoverStorageDep,
    CredentialVaultDep,
    CurrentUserIdDep,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api", tags=["covers"])

_KEYLESS_DETAIL = (
    "AI cover generation needs an OpenAI API key — add one in Settings. Without it, courses show "
    "the Typographic cover."
)


async def require_keyed_cover_caller(owner_id: CurrentUserIdDep, vault: CredentialVaultDep) -> str:
    """The keyed-only tier gate for enqueue: AI covers need the caller's OpenAI key.

    Mirrors the video gate's credential ladder — with a vault (auth + BYOK) the caller's own OpenAI
    key decides; without one, the process env does (single-user / auth-off deployments). A keyless
    caller gets a 403, so the web never enqueues for them and shows the Typographic cover."""
    if vault is not None:
        keyed = bool(await vault.reveal(user_id=owner_id, provider="openai"))
    else:
        keyed = bool(os.environ.get("OPENAI_API_KEY"))
    if not keyed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_KEYLESS_DETAIL)
    return owner_id


class CoverJobView(CourseModel):
    """The wire shape of one cover job: the row itself, short-lived signed image URLs once the cover
    is READY, and the structural provenance (the anti-slop record — which models drew and inspected
    it). A non-READY job carries just the row so the reader can render its progress.

    ``image_url`` is the DARK cover; ``image_url_light`` is its LIGHT-theme twin (dual-theme
    covers) and is ``None`` for a dark-only cover — the web shows the dark image in the app's light
    theme and the light image in its dark theme (an inverted/contrast mapping), falling back to the
    dark image when there is no light one.

    Each variant also carries a ``thumb_url`` — the SAME artwork, resized by storage to display
    size (``COVER_DISPLAY_TRANSFORM``). The card and Overview frames render the thumb; only the
    full-size lightbox loads the master. The thumb dimension is orthogonal to light/dark, so a
    dual-theme cover carries two of each. A reader that gets no thumb (an older client, or storage
    without image transformations) falls back to the master — the field is additive, never
    required."""

    job: CoverJob
    image_url: str | None = None
    image_url_light: str | None = None
    thumb_url: str | None = None
    thumb_url_light: str | None = None
    provenance: CoverProvenance | None = None


async def _load_owned_course(
    store: ICourseStore, *, course_id: str, owner_id: str, request_id: str
) -> Course:
    """The course if the caller owns it, else 404. ``load`` is owner-scoped and raises
    ``FileNotFoundError`` for a missing OR not-owned course (existence never leaks across tenants);
    it's synchronous (file / blocking supabase-py), so it's off-loaded to keep the loop free. The
    404 carries ``X-Request-Id`` on the ``HTTPException`` itself — Starlette builds the error
    response from the exception, discarding the mutated request-scoped ``Response``, so correlation
    would otherwise be dropped on exactly the failure path that needs it."""
    try:
        return await asyncio.to_thread(lambda: store.load(course_id, owner_id=owner_id))
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
            headers={"X-Request-Id": request_id},
        ) from None


@router.post("/courses/{course_id}/cover", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_cover(
    course_id: str,
    owner_id: Annotated[str, Depends(require_keyed_cover_caller)],
    queue: CoverJobQueueDep,
    store: CourseStoreDep,
    response: Response,
) -> CoverJobView:
    """Enqueue one course cover-image job. The worker drains it; the job row is the status record.

    Gates: the caller must have an **OpenAI key** (else 403 — a keyless account shows the
    Typographic cover and never enqueues), must **own** the course (else 404 — never spend worker
    capacity on a course you don't own), and a **duplicate** is deduped (idempotent). One cover per
    course, so the dedup keys on (course, owner) with no kind/lesson dimension."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    course = await _load_owned_course(
        store, course_id=course_id, owner_id=owner_id, request_id=request_id
    )
    # Deliberate asymmetry (AD): the MANUAL enqueue always uses the house default preset; only
    # the build-completion auto-enqueue honors the per-user coverStylePreset config. Threading
    # the user config store into this router is a follow-up if per-preset manual enqueue is
    # ever wanted — Regenerate already preserves each cover's own preset.
    job, created = await enqueue_cover_job(
        queue, course=course, owner_id=owner_id, style_preset=CoverStylePreset.GENERAL
    )
    logger.info(
        "cover_job_enqueued" if created else "cover_job_enqueue_deduped",
        job_id=job.id,
        course_id=course_id,
    )
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
        # 404 for missing AND not-owned alike — existence is never leaked across tenants. The header
        # rides on the exception (Starlette discards the mutated Response on an error path).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover job not found",
            headers={"X-Request-Id": request_id},
        )
    return await _cover_job_view(job, storage)


@router.get(
    "/covers/{job_id}/active",
    response_model=CoverJobView,
    responses={204: {"description": "No cover in flight or newer than the source for the course"}},
)
async def get_active_cover_job(
    job_id: str,
    owner_id: CurrentUserIdDep,
    queue: CoverJobQueueDep,
    storage: CoverStorageDep,
    response: Response,
) -> CoverJobView | Response:
    """The course's currently in-flight cover job, so the reader re-attaches to a (re)generate it
    started but no longer holds the id for — navigate away + back, refresh, or a regenerate whose
    new job_id the persisted ``Course.cover`` handle doesn't know.

    Keyed by the SOURCE job the reader DOES hold (``Course.cover.job_id``): its ``course_id``
    locates the course, and ``find_active`` returns the live cover job for it — the source itself
    while it is still generating, or a newer regenerate. **204** when nothing is in flight AND the
    latest READY cover is the source (the reader keeps its terminal state); a settled regenerate
    newer than the source is surfaced (with its signed URL + provenance) so a completed regenerate
    persists. **404** when the source job is unknown or not owned (existence never leaks across
    tenants). Owner-scoped, NOT tier-gated — like the status poll, re-attaching to your own cover
    consumes no generation capacity."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    source = await queue.get(job_id=job_id, owner_id=owner_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover job not found",
            headers={"X-Request-Id": request_id},
        )
    active = await queue.find_active(course_id=source.course_id, owner_id=owner_id)
    if active is not None:
        return await _cover_job_view(active, storage)
    # Nothing in flight: surface the course's latest SUCCESSFUL cover if it is a newer take than the
    # source the reader holds (a completed regenerate the persisted handle does not point to). This
    # is what makes a successful regenerate persist — the reader re-resolves it on every mount.
    latest_ready = await queue.find_latest_ready(course_id=source.course_id, owner_id=owner_id)
    if latest_ready is not None and latest_ready.id != source.id:
        return await _cover_job_view(latest_ready, storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Request-Id": request_id})


@router.post("/covers/{job_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_cover(
    job_id: str,
    owner_id: Annotated[str, Depends(require_keyed_cover_caller)],
    queue: CoverJobQueueDep,
    store: CourseStoreDep,
    response: Response,
) -> CoverJobView:
    """Regenerate a course's cover — a fresh art-direction + render, keyed by the source cover job.

    Gates like enqueue: the caller must have an **OpenAI key** (else 403) and **own** the source job
    (else 404 — existence never leaks across tenants). A regenerate already in flight for the course
    is returned rather than stacked (idempotent). The new job re-fingerprints the CURRENT course
    topic under the source's style preset, so it reflects any topic change since the last cover. It
    is enqueued QUEUED; the worker drains it exactly like an initial cover."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    source = await queue.get(job_id=job_id, owner_id=owner_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover job not found",
            headers={"X-Request-Id": request_id},
        )
    course = await _load_owned_course(
        store, course_id=source.course_id, owner_id=owner_id, request_id=request_id
    )
    # Regenerate preserves the source's preset and re-fingerprints the CURRENT course topic; the
    # shared helper dedups an in-flight regenerate rather than stacking a second.
    job, created = await enqueue_cover_job(
        queue, course=course, owner_id=owner_id, style_preset=source.style_preset
    )
    logger.info(
        "cover_job_regenerate_enqueued" if created else "cover_job_regenerate_deduped",
        job_id=job.id,
        source_job_id=source.id,
    )
    return CoverJobView(job=job)


@router.post("/covers/{job_id}/cancel")
async def cancel_cover_job(
    job_id: str,
    owner_id: CurrentUserIdDep,
    queue: CoverJobQueueDep,
    response: Response,
) -> CoverJobView:
    """Stop a cover the caller owns before it finishes — a queued job is then never claimed, and an
    in-flight one is aborted by the worker's cancel-watcher, so no compute is spent on a stopped
    cover.

    Owner-scoped: the job must exist and be owned, else 404. Deliberately NOT tier-gated (unlike
    enqueue/regenerate): stopping your own job consumes no generation capacity, so a user whose key
    was removed mid-flight must still be able to stop it. Idempotent: cancelling an already-terminal
    job is a no-op that returns its current state. Returns the job so the reader can show the
    stopped state and offer a regenerate."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    job = await queue.get(job_id=job_id, owner_id=owner_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover job not found",
            headers={"X-Request-Id": request_id},
        )
    transitioned = await queue.cancel(job_id=job_id, owner_id=owner_id)
    # Re-read only when the cancel actually transitioned the row; an idempotent no-op (already
    # terminal) leaves the first read as the current truth. Either way it is this caller's own row.
    if transitioned:
        settled = await queue.get(job_id=job_id, owner_id=owner_id)
        if settled is not None:
            job = settled
    logger.info(
        "cover_job_cancel", job_id=job_id, status=job.status.value, transitioned=transitioned
    )
    return CoverJobView(job=job)


async def _cover_job_view(job: CoverJob, storage: ICoverStorage) -> CoverJobView:
    """The wire view of a cover job: a READY job carries short-lived signed image URL(s) and the
    structural provenance (resolved on demand, never persisted stale); any other status is the bare
    row so the reader renders its progress. Shared by the status, active and (indirectly) enqueue
    surfaces so they thread provenance identically.

    Each variant is minted TWICE: the master (for the full-size lightbox) and a storage-resized
    derivative (for the card and Overview frames, which would otherwise make the browser downscale a
    2048px master into a 260px box — the thing that makes a card cover look soft). The mints are
    independent, so they are gathered rather than awaited in turn.

    A dual-theme cover also carries the ``*_light`` URLs — minted ONLY when ``provenance`` says a
    light variant exists, so a signed URL is never requested for a missing object (a dark-only or
    pre-dual-theme cover has no ``cover-light.png``)."""
    if job.status != CoverJobStatus.READY:
        return CoverJobView(job=job)
    paths = CoverArtifactPaths.for_job(job)
    image_url, thumb_url, provenance = await asyncio.gather(
        storage.signed_url(path=paths.image),
        _mint_thumb(storage, paths.image),
        _read_provenance(storage, paths.provenance),
    )
    image_url_light: str | None = None
    thumb_url_light: str | None = None
    if provenance is not None and provenance.has_light_variant:
        image_url_light, thumb_url_light = await asyncio.gather(
            storage.signed_url(path=paths.image_light),
            _mint_thumb(storage, paths.image_light),
        )
    return CoverJobView(
        job=job,
        image_url=image_url,
        image_url_light=image_url_light,
        thumb_url=thumb_url,
        thumb_url_light=thumb_url_light,
        provenance=provenance,
    )


async def _mint_thumb(storage: ICoverStorage, path: str) -> str | None:
    """The display-size derivative's signed URL — best effort.

    The derivative is an OPTIMIZATION (a sharp, ~20x lighter card image), not the cover itself, so a
    storage backend that cannot resize — image transformations disabled, a transform-specific quota
    or hiccup — must not take down the whole view along with the master URL and provenance that
    resolved fine beside it. Degrading to ``None`` is exactly what the reader's load ladder expects:
    it falls back to the master, and the cover still renders (softer, not missing)."""
    try:
        return await storage.signed_url(path=path, transform=COVER_DISPLAY_TRANSFORM)
    except PersistenceError as exc:
        logger.warning("cover_thumb_unavailable", path=path, reason=type(exc).__name__)
        return None


async def _read_provenance(storage: ICoverStorage, path: str) -> CoverProvenance | None:
    """The cover's structural provenance, threaded onto the wire. Supplementary to display, so a
    missing or malformed artifact degrades to None, never a 500."""
    try:
        return CoverProvenance.model_validate_json(await storage.download(path=path))
    except (PersistenceError, ValidationError) as exc:
        logger.warning("cover_provenance_unavailable", path=path, reason=type(exc).__name__)
        return None
