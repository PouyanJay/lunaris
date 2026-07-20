import asyncio
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from lunaris_runtime.logging import bind_request_id
from lunaris_runtime.persistence import (
    ICourseStore,
    IVideoStorage,
    PersistenceError,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import (
    Lesson,
    RegenerateMode,
    VideoJob,
    VideoJobStatus,
    VideoKind,
    VideoProvenance,
)
from lunaris_runtime.schema.base import CourseModel
from lunaris_runtime.video_build import (
    VideoConfig,
    lesson_video_input_hash,
    video_config_from_map,
    video_input_hash,
)
from lunaris_video.assembly import build_video_outline
from lunaris_video.schemas import SceneContracts, TimingManifest
from pydantic import Field, ValidationError

from ..config import Settings, get_settings
from ..dependencies import (
    CourseStoreDep,
    CredentialVaultDep,
    CurrentUserIdDep,
    UserConfigStoreDep,
    VideoJobQueueDep,
    VideoStorageDep,
    explain_is_available,
)
from ..user_config import to_env_map

logger = structlog.get_logger()

router = APIRouter(prefix="/api", tags=["videos"])

_KEYLESS_DETAIL = (
    "Video generation needs an Anthropic API key — add one in Settings. "
    "The Draft tier does not include videos."
)

_VIDEO_DISABLED_DETAIL = (
    "Video generation is turned off in your settings. Turn it on to generate videos."
)


async def caller_video_config(owner_id: CurrentUserIdDep, store: UserConfigStoreDep) -> VideoConfig:
    """The caller's resolved video config — the on-demand mirror of the build path's run-config
    resolution, gating enqueue on the master toggle and stamping the chosen length + voice."""
    return video_config_from_map(to_env_map(await store.get_all(user_id=owner_id)))


VideoConfigDep = Annotated[VideoConfig, Depends(caller_video_config)]


class VideoChapterView(CourseModel):
    """One chapter of a ready video (Cinema): a scene surfaced as a navigable chapter with its
    span on the concatenated timeline. ``start_s``/``end_s`` come from the timing manifest; the
    title is the scene's authored title when present, else a derived label."""

    id: str
    title: str
    start_s: float
    end_s: float


class TranscriptCueView(CourseModel):
    """One transcript cue of a ready video (Cinema): a spoken beat with its timed span, so the web
    can render a synced, click-to-seek transcript. Empty for a silent (un-narrated) video."""

    start_s: float
    end_s: float
    text: str


class VideoJobView(CourseModel):
    """The wire shape of one video job: the row itself, playback URLs, a captions URL (narrated
    videos only), the grounding provenance once it is ready, whether the lesson it was built
    from has since been revised (``stale`` — the reader's "outdated" badge, V6-T3), and — once
    ready — the Cinema outline: navigable ``chapters`` and a timed ``transcript`` derived from the
    video's scene contracts + timing manifest (empty on a job that isn't ready)."""

    job: VideoJob
    video_url: str | None = None
    poster_url: str | None = None
    captions_url: str | None = None
    provenance: VideoProvenance | None = None
    stale: bool = False
    chapters: list[VideoChapterView] = Field(default_factory=list)
    transcript: list[TranscriptCueView] = Field(default_factory=list)


class CourseVideoStatus(CourseModel):
    """One video job's lean status for the build canvas's "Videos N/M" progress: just the slot
    coordinates + status, no config/grounding snapshots (which the full ``VideoJob`` carries)."""

    job_id: str
    kind: VideoKind
    lesson_id: str | None = None
    status: VideoJobStatus


class RegenerateRequest(CourseModel):
    """Body of a regenerate request: which of the four menu modes to re-run (V6-T2)."""

    mode: RegenerateMode


_REUSE_UNAVAILABLE_DETAIL = (
    "This video hasn't finished yet — use Fresh take or Simpler to generate it."
)


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
    video_config: VideoConfigDep,
    queue: VideoJobQueueDep,
    store: CourseStoreDep,
    response: Response,
) -> VideoJobView:
    """Enqueue one lesson-video job. The worker drains it; the job row is the status record.

    Gates (plan §V6 — the per-user master toggle gates every enqueue point): video must be on in the
    caller's settings (else 403), the caller must **own** the course and the lesson must exist in it
    (else 404 — never spend worker capacity on a course you don't own), and a **duplicate** is
    deduped (idempotent Generate). The enqueued job carries the tenant's chosen lesson length + the
    voice toggle, so the worker plans to the right length and narrates only when asked (V6)."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    if not video_config.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_VIDEO_DISABLED_DETAIL)
    lesson = await _load_owned_lesson(
        store, course_id=course_id, lesson_id=lesson_id, owner_id=owner_id
    )
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
        # Fold the lesson's content + chosen length into the input hash so the staleness check can
        # later flag the video outdated once the lesson is revised (V6-T3).
        input_hash=lesson_video_input_hash(
            course_id, lesson, target_seconds=video_config.target_seconds(VideoKind.LESSON)
        ),
        config={
            "target_seconds": video_config.target_seconds(VideoKind.LESSON),
            "voice": video_config.voice,
        },
    )
    await queue.enqueue(job)
    logger.info("video_job_enqueued", job_id=job.id, course_id=course_id, lesson_id=lesson_id)
    return VideoJobView(job=job)


@router.post(
    "/videos/{job_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_video_generation_enabled)],
)
async def regenerate_video(
    job_id: str,
    payload: RegenerateRequest,
    owner_id: Annotated[str, Depends(require_keyed_caller)],
    video_config: VideoConfigDep,
    queue: VideoJobQueueDep,
    store: CourseStoreDep,
    response: Response,
) -> VideoJobView:
    """Re-run a video through the regenerate menu (plan §V6-T2). Works for any kind (lesson /
    summary / overview), keyed by the source job.

    Each mode re-enters the pipeline at the right node: ``RETRY`` / ``ADD_NARRATION`` reuse the
    source's planned contract (so they need a finished source — else 409), ``SIMPLER`` / ``FRESH``
    re-plan. The new job inherits the source's coordinates + grounding snapshot (course videos plan
    against it, AD-1) and the source's contract path (for the reuse modes); its length + voice come
    from the owner's current config, except ``ADD_NARRATION`` forces narration on. A regenerate
    already in flight for these coordinates is returned rather than stacked."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    if not video_config.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_VIDEO_DISABLED_DETAIL)
    source = await queue.get(job_id=job_id, owner_id=owner_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video job not found")
    if payload.mode.reuses_contract and source.status is not VideoJobStatus.READY:
        # No finished contract to re-render — a 409 the reader maps to "use Fresh take / Simpler".
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_REUSE_UNAVAILABLE_DETAIL)
    existing = await queue.find_active(
        course_id=source.course_id,
        lesson_id=source.lesson_id,
        kind=source.kind,
        owner_id=owner_id,
    )
    if existing is not None:
        logger.info("video_job_regenerate_deduped", job_id=existing.id, source_job_id=source.id)
        return VideoJobView(job=existing)
    # The regenerated lesson video is built from the CURRENT lesson, so it fingerprints the current
    # content + length — otherwise it would read "outdated" the instant it finished (V6-T3).
    input_hash = await _regenerate_input_hash(store, source, video_config)
    new_job = _regenerate_job(source, payload.mode, video_config, owner_id, input_hash)
    await queue.enqueue(new_job)
    logger.info(
        "video_job_regenerate_enqueued",
        job_id=new_job.id,
        source_job_id=source.id,
        mode=payload.mode.value,
    )
    return VideoJobView(job=new_job)


@router.post(
    "/videos/{job_id}/cancel",
    dependencies=[Depends(require_video_generation_enabled)],
)
async def cancel_video_job(
    job_id: str,
    owner_id: CurrentUserIdDep,
    queue: VideoJobQueueDep,
    response: Response,
) -> VideoJobView:
    """Stop a video the caller owns before it finishes — a queued job is then never claimed, and an
    in-flight one is aborted by the worker's cancel-watcher (its render subprocess killed), so no
    compute is spent on a stopped video.

    Owner-scoped: the job must exist and be owned, else 404 (existence never leaks across tenants).
    Deliberately NOT tier-gated and NOT per-user-master-toggle gated (unlike enqueue/regenerate):
    stopping your own job consumes no generation capacity, so a user whose key was removed — or who
    turned video off in Settings — mid-flight must still be able to stop an in-flight job. The
    operator kill-switch still applies (404 when ``VIDEO_GENERATION_ENABLED`` is off, like every
    video route — the surface is then absent, and nothing is rendering to stop). Idempotent:
    cancelling an already-terminal job is a no-op that returns its current state. Returns the job so
    the reader can show the stopped state and offer a restart."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    job = await queue.get(job_id=job_id, owner_id=owner_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video job not found",
            headers={"X-Request-Id": request_id},
        )
    transitioned = await queue.cancel(job_id=job_id, owner_id=owner_id)
    # Re-read only when the cancel actually transitioned the row; an idempotent no-op (the job was
    # already terminal) leaves the first read as the current truth. Either way the owner-scoped read
    # is this caller's own row, never another tenant's.
    if transitioned:
        settled = await queue.get(job_id=job_id, owner_id=owner_id)
        if settled is not None:
            job = settled
    logger.info(
        "video_job_cancel", job_id=job_id, status=job.status.value, transitioned=transitioned
    )
    return VideoJobView(job=job)


def _regenerate_job(
    source: VideoJob,
    mode: RegenerateMode,
    video_config: VideoConfig,
    owner_id: str,
    input_hash: str,
) -> VideoJob:
    """The new job a regenerate enqueues: the source's coordinates + grounding snapshot, the owner's
    current length, the resolved voice (forced on for Add narration), the freshly recomputed input
    hash, and the regenerate descriptor (the mode + the contract path for the reuse modes)."""
    config: dict[str, object] = {}
    grounding = source.config.get("grounding")
    if grounding is not None:
        config["grounding"] = grounding  # course videos plan against their own snapshot (AD-1)
    config["target_seconds"] = video_config.target_seconds(source.kind)
    config["voice"] = True if mode is RegenerateMode.ADD_NARRATION else video_config.voice
    regenerate: dict[str, object] = {"mode": mode.value, "source_job_id": source.id}
    if mode.reuses_contract:
        # Only the reuse modes read the source's contract; re-plan modes ignore it.
        regenerate["contract_path"] = VideoArtifactPaths.for_job(source).contracts
    config["regenerate"] = regenerate
    return VideoJob(
        id=uuid.uuid4().hex,
        user_id=owner_id,
        course_id=source.course_id,
        lesson_id=source.lesson_id,
        kind=source.kind,
        input_hash=input_hash,
        config=config,
    )


async def _regenerate_input_hash(
    store: ICourseStore, source: VideoJob, video_config: VideoConfig
) -> str:
    """The input hash the regenerated job is built under: a LESSON re-fingerprints the current
    lesson + length (so a Fresh/Simpler regenerate clears the outdated badge); a course video (no
    lesson) re-fingerprints its current length; a vanished lesson keeps the source's hash."""
    if source.kind is not VideoKind.LESSON or source.lesson_id is None:
        # Course videos have no per-lesson content — re-fingerprint the current length only.
        return video_input_hash(
            source.course_id,
            source.kind.value,
            target_seconds=video_config.target_seconds(source.kind),
        )
    lesson = await _find_lesson(
        store, course_id=source.course_id, lesson_id=source.lesson_id, owner_id=source.user_id
    )
    if lesson is None:
        return source.input_hash
    return lesson_video_input_hash(
        source.course_id, lesson, target_seconds=video_config.target_seconds(VideoKind.LESSON)
    )


async def _find_lesson(
    store: ICourseStore, *, course_id: str, lesson_id: str, owner_id: str
) -> Lesson | None:
    """The owner's lesson, or ``None`` if the course / lesson is missing or not owned. ``load`` is
    owner-scoped and raises ``FileNotFoundError`` for a missing OR not-owned course (so a not-found
    answer never leaks another tenant's course); it's synchronous (file / blocking supabase-py), so
    it's off-loaded to keep the event loop free. The single course-load + lesson-find the enqueue
    guard, the staleness check, and the regenerate recompute all share."""
    try:
        course = await asyncio.to_thread(lambda: store.load(course_id, owner_id=owner_id))
    except FileNotFoundError:
        return None
    return next(
        (
            lesson
            for module in course.modules
            for lesson in module.lessons
            if lesson.id == lesson_id
        ),
        None,
    )


async def _load_owned_lesson(
    store: ICourseStore, *, course_id: str, lesson_id: str, owner_id: str
) -> Lesson:
    """The lesson if the caller owns the course and it contains the lesson, else 404. Returning it
    lets enqueue fingerprint its content for the staleness key (V6-T3)."""
    lesson = await _find_lesson(store, course_id=course_id, lesson_id=lesson_id, owner_id=owner_id)
    if lesson is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found")
    return lesson


async def _lesson_video_stale(
    store: ICourseStore, job: VideoJob, video_config: VideoConfig
) -> bool:
    """Whether a READY lesson video is outdated: recompute its input hash from the lesson's CURRENT
    content + the caller's CURRENT length and compare to the hash it was built under (V6-T3). A
    course-level video (no lesson to revise) or a missing course/lesson → not stale (the badge only
    fires on a clear mismatch, never a guess)."""
    if job.kind is not VideoKind.LESSON or job.lesson_id is None:
        return False
    lesson = await _find_lesson(
        store, course_id=job.course_id, lesson_id=job.lesson_id, owner_id=job.user_id
    )
    if lesson is None:
        return False
    current = lesson_video_input_hash(
        job.course_id, lesson, target_seconds=video_config.target_seconds(VideoKind.LESSON)
    )
    return current != job.input_hash


@router.get(
    "/courses/{course_id}/videos",
    response_model=list[CourseVideoStatus],
    dependencies=[Depends(require_video_generation_enabled)],
)
async def list_course_video_jobs(
    course_id: str,
    owner_id: CurrentUserIdDep,
    queue: VideoJobQueueDep,
    response: Response,
) -> list[CourseVideoStatus]:
    """Every video job the course enqueued, lean (id, kind, lesson, status) — drives the build
    canvas's "Videos N/M" phase after the build run completes (the videos render async on the cloud
    worker, minutes after delivery, so the build SSE has already ended). An empty list when the
    course built no videos (a video-off build) — 200, not 404, so the canvas just shows no phase.

    Owner-scoped via ``list_for_course`` (another tenant's course reads as empty, never leaking
    existence). NOT tier-gated, like the status poll: reading your own jobs' status consumes no
    generation capacity. Behind the operator kill-switch (404 when video is off entirely)."""
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    jobs = await queue.list_for_course(course_id=course_id, owner_id=owner_id)
    return [
        CourseVideoStatus(job_id=job.id, kind=job.kind, lesson_id=job.lesson_id, status=job.status)
        for job in jobs
    ]


@router.get(
    "/courses/{course_id}/videos/active",
    response_model=VideoJobView,
    responses={204: {"description": "No job for the slot"}},
    dependencies=[Depends(require_video_generation_enabled)],
)
async def get_active_video_job_by_coordinates(
    course_id: str,
    owner_id: CurrentUserIdDep,
    queue: VideoJobQueueDep,
    response: Response,
    kind: Annotated[VideoKind, Query()],
    lesson_id: Annotated[str | None, Query(alias="lessonId")] = None,
) -> VideoJobView | Response:
    """The slot's live video job keyed by its COORDINATES (course, lesson, kind), so the reader
    resolves a slot it holds no job id for — a build whose course payload pointer is null, or
    FAILED-with-a-job-that-has-since-gone-READY (the async-after-delivery case: the cloud worker
    finishes a video minutes after finalize wrote the FAILED pointer, and nothing rewrites it).

    Why this exists alongside ``/videos/{job_id}/active``: that sibling keys on a SOURCE job id and
    only surfaces a *newer* take (``latest_ready.id != source.id``), so when the source job ITSELF
    transitioned FAILED→READY it answers 204 and the reader stays stuck on "Couldn't generate". This
    probe needs no source id — it returns the slot's in-flight job (``find_active``) or, failing
    that, its latest finished render (``find_latest_ready``); **204** when the slot has neither.

    Like the sibling probe this answers *which* job is the slot's current one — the bare job row,
    no signed URLs. The reader exchanges that id for playback URLs via ``GET /videos/{job_id}`` (the
    same follow-up it already does after the source-id probe), so URL minting stays in one place.

    Owner-scoped via the queue queries (a slot with no jobs for the caller — another tenant's
    course, or a video-off build — reads as 204, never leaking existence). NOT tier-gated, like the
    status poll: re-attaching to your own slot consumes no generation capacity. ``active`` is a
    fixed path segment; any future ``/courses/{course_id}/videos/{video_id}`` route must be declared
    after this one so it never shadows the probe.
    """
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id
    # In flight beats finished: a live (re)generate will settle, so the reader should follow it
    # rather than an older READY take. With nothing in flight, the latest finished render is it.
    active = await queue.find_active(
        course_id=course_id, lesson_id=lesson_id, kind=kind, owner_id=owner_id
    )
    if active is not None:
        return VideoJobView(job=active)
    latest_ready = await queue.find_latest_ready(
        course_id=course_id, lesson_id=lesson_id, kind=kind, owner_id=owner_id
    )
    if latest_ready is not None:
        return VideoJobView(job=latest_ready)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Request-Id": request_id})


@router.get(
    "/videos/{job_id}/active",
    response_model=VideoJobView,
    responses={204: {"description": "No job in flight for the slot"}},
    dependencies=[Depends(require_video_generation_enabled)],
)
async def get_active_video_job(
    job_id: str,
    owner_id: CurrentUserIdDep,
    queue: VideoJobQueueDep,
    response: Response,
) -> VideoJobView | Response:
    """The slot's currently in-flight job, so the reader re-attaches to a (re)generate it started
    but no longer holds the id for — navigate away + back, refresh, or a regenerate whose new
    job_id the persisted artifact doesn't know (the "nothing happening" bug).

    Keyed by the SOURCE job the reader DOES hold (``resolveJobId`` of the persisted artifact): its
    (course, lesson, kind) coordinates locate the slot, and ``find_active`` returns the live job
    for those coordinates — the source itself while it is still rendering, or a newer regenerate.
    **204** when nothing is in flight (the reader keeps its terminal state); **404** when the source
    job is unknown or not owned (existence never leaks across tenants). Owner-scoped, NOT tier-gated
    — like the status poll, re-attaching to your own job consumes no generation capacity.
    """
    request_id = uuid.uuid4().hex
    bind_request_id(request_id)
    response.headers["X-Request-Id"] = request_id  # stamped before any 404, like the sibling routes
    source = await queue.get(job_id=job_id, owner_id=owner_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video job not found",
            headers={"X-Request-Id": request_id},
        )
    active = await queue.find_active(
        course_id=source.course_id,
        lesson_id=source.lesson_id,
        kind=source.kind,
        owner_id=owner_id,
    )
    if active is not None:
        return VideoJobView(job=active)
    # Nothing in flight: surface the slot's latest SUCCESSFUL render if it is a newer take than the
    # source the reader holds (a completed regenerate the persisted artifact does not point to).
    # This is what makes a successful regenerate persist — the reader re-resolves it on every mount
    # instead of reverting to the stale failed/old built artifact when the live job has settled.
    latest_ready = await queue.find_latest_ready(
        course_id=source.course_id,
        lesson_id=source.lesson_id,
        kind=source.kind,
        owner_id=owner_id,
    )
    if latest_ready is not None and latest_ready.id != source.id:
        return VideoJobView(job=latest_ready)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Request-Id": request_id})


@router.get(
    "/videos/{job_id}",
    dependencies=[Depends(require_video_generation_enabled)],
)
async def get_video_job(
    job_id: str,
    owner_id: CurrentUserIdDep,
    video_config: VideoConfigDep,
    queue: VideoJobQueueDep,
    storage: VideoStorageDep,
    store: CourseStoreDep,
    response: Response,
) -> VideoJobView:
    """One job's status, owner-scoped; a READY job carries short-lived signed playback URLs and the
    staleness flag (whether its lesson has since been revised — the reader's outdated badge, V6-T3).

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
    # The reads are independent — gather them so a READY status poll is one round-trip's worth of
    # latency, not several sequential ones. Staleness re-loads the course to fingerprint the current
    # lesson, so it joins the gather rather than serialising behind the signed-URL reads.
    video_url, poster_url, captions_url, provenance, stale, outline = await asyncio.gather(
        storage.signed_url(path=paths.mp4),
        storage.signed_url(path=paths.poster),
        _captions_url_if_narrated(storage, paths),
        _read_provenance(storage, paths.provenance),
        _lesson_video_stale(store, job, video_config),
        _read_outline(storage, paths),
    )
    chapters, transcript = outline
    return VideoJobView(
        job=job,
        video_url=video_url,
        poster_url=poster_url,
        captions_url=captions_url,
        provenance=provenance,
        stale=stale,
        chapters=chapters,
        transcript=transcript,
    )


async def _read_outline(
    storage: IVideoStorage, paths: VideoArtifactPaths
) -> tuple[list[VideoChapterView], list[TranscriptCueView]]:
    """The Cinema outline (chapters + timed transcript), derived from the scene contracts + timing
    manifest the ready job persisted. Supplementary to playback, so a missing or malformed artifact
    — absent (pre-Cinema render), schema drift, or a contracts/timing pair whose scene or beat ids
    disagree (KeyError in the walk) — degrades to empty, never a 500."""
    try:
        contracts = SceneContracts.model_validate_json(await storage.download(path=paths.contracts))
        manifest = TimingManifest.model_validate_json(await storage.download(path=paths.timing))
        outline = build_video_outline(contracts, manifest)
    except (PersistenceError, ValidationError, KeyError) as exc:
        logger.warning(
            "video_outline_unavailable",
            contracts_path=paths.contracts,
            timing_path=paths.timing,
            reason=type(exc).__name__,
        )
        return [], []
    chapters = [
        VideoChapterView(id=c.id, title=c.title, start_s=c.start_s, end_s=c.end_s)
        for c in outline.chapters
    ]
    transcript = [
        TranscriptCueView(start_s=cue.start_s, end_s=cue.end_s, text=cue.text)
        for cue in outline.transcript
    ]
    return chapters, transcript


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
