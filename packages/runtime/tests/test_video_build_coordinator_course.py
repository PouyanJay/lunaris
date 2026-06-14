"""Video V5-T2: the build coordinator's course-level methods (``QueueVideoBuildCoordinator``).

The SUMMARY trailer + OVERVIEW intro enqueue once the curriculum is designed, carrying their
grounding snapshot ON the job (the course isn't persisted until finalize — AD-1), and finalize
awaits them via ``collect_course_videos``, degrading each to its OWN kind so the Overview shows the
right retry state."""

from lunaris_runtime.persistence import (
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import (
    CourseBrief,
    Module,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
    VideoArtifact,
    VideoJobStatus,
    VideoKind,
    VideoProvenance,
)
from lunaris_runtime.video_build import (
    QueueVideoBuildCoordinator,
    VideoConfig,
    target_seconds_for,
    video_input_hash,
)

_OWNER = "user-a"


def _video_config(*, voice: bool = True) -> VideoConfig:
    return VideoConfig(
        enabled=True,
        voice=voice,
        summary_seconds=target_seconds_for(VideoKind.SUMMARY),
        overview_seconds=target_seconds_for(VideoKind.OVERVIEW),
        lesson_seconds=target_seconds_for(VideoKind.LESSON),
    )


def _coordinator(
    queue: object, storage: object | None = None, **kwargs: object
) -> QueueVideoBuildCoordinator:
    return QueueVideoBuildCoordinator(
        queue=queue, storage=storage or InMemoryVideoStorage(), owner_id=_OWNER, **kwargs
    )


def _modules() -> list[Module]:
    return [Module(id="m1", title="Sorting"), Module(id="m2", title="Searching")]


def _brief() -> CourseBrief:
    return CourseBrief(
        subject="Algorithms",
        goal="reason about cost",
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=["analyse Big-O"],
            sources=[ResearchSource(url="https://x/clrs", title="CLRS")],
        ),
    )


# ── enqueue ───────────────────────────────────────────────────────────────────────────


async def test_enqueue_summary_stamps_kind_length_and_curriculum_grounding() -> None:
    # Arrange — the tenant turned narration OFF (a silent trailer).
    queue = InMemoryVideoJobQueue()
    coordinator = _coordinator(queue, video_config=_video_config(voice=False))

    # Act
    job_id = await coordinator.enqueue_summary(
        course_id="c1", topic="Algorithms", modules=_modules()
    )

    # Assert — a QUEUED course-level SUMMARY job (no lesson) at the summary length, carrying the
    # curriculum grounding the worker plans against without the not-yet-persisted course.
    assert job_id is not None
    job = await queue.get(job_id=job_id, owner_id=_OWNER)
    assert job is not None
    assert job.kind is VideoKind.SUMMARY
    assert job.lesson_id is None
    assert job.status is VideoJobStatus.QUEUED
    assert job.config["target_seconds"] == target_seconds_for(VideoKind.SUMMARY)
    assert job.config["voice"] is False  # the tenant's voice toggle is stamped on the job
    grounding = job.config["grounding"]
    assert grounding["topic"] == "Algorithms"
    assert [m["title"] for m in grounding["modules"]] == ["Sorting", "Searching"]
    # The course-video input hash folds the kind's length (V6-T3); no per-lesson content_hash.
    assert job.input_hash == video_input_hash(
        "c1", "summary", target_seconds=target_seconds_for(VideoKind.SUMMARY)
    )


async def test_enqueue_overview_stamps_kind_length_and_brief_grounding() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    coordinator = _coordinator(queue)

    # Act
    job_id = await coordinator.enqueue_overview(course_id="c1", brief=_brief())

    # Assert — a QUEUED OVERVIEW job at the ~3-min length, carrying the whole brief (with its
    # researched standard) so the intro grounds in the moat, not the model's memory.
    assert job_id is not None
    job = await queue.get(job_id=job_id, owner_id=_OWNER)
    assert job is not None
    assert job.kind is VideoKind.OVERVIEW
    assert job.config["target_seconds"] == target_seconds_for(VideoKind.OVERVIEW)
    brief = job.config["grounding"]["brief"]
    assert brief["subject"] == "Algorithms"
    assert brief["research"]["competencies"] == ["analyse Big-O"]


async def test_course_videos_are_idempotent_within_a_build() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    coordinator = _coordinator(queue)

    # Act — enqueue each kind twice (a defensive re-call).
    summary_first = await coordinator.enqueue_summary(course_id="c1", topic="t", modules=_modules())
    summary_second = await coordinator.enqueue_summary(
        course_id="c1", topic="t", modules=_modules()
    )
    overview_first = await coordinator.enqueue_overview(course_id="c1", brief=_brief())
    overview_second = await coordinator.enqueue_overview(course_id="c1", brief=_brief())

    # Assert — one job per kind; exactly two rows claimable.
    assert summary_first == summary_second
    assert overview_first == overview_second
    claimed = {(await queue.claim(worker_id="w")).kind for _ in range(2)}  # type: ignore[union-attr]
    assert claimed == {VideoKind.SUMMARY, VideoKind.OVERVIEW}
    assert await queue.claim(worker_id="w") is None


# ── collect ───────────────────────────────────────────────────────────────────────────


def _ready(kind: VideoKind, job_id: str) -> VideoArtifact:
    return VideoArtifact(
        kind=kind,
        status=VideoJobStatus.READY,
        provenance=VideoProvenance(
            job_id=job_id,
            course_id="c1",
            lesson_id=None,
            kind=kind,
            model="stub",
            contract_hash="h",
            input_hash="h",
            generated_at="2026-01-01T00:00:00+00:00",
        ),
        duration_s=80.0,
    )


async def test_collect_course_videos_returns_ready_artifacts_keyed_by_kind() -> None:
    # Arrange — both course videos enqueued, their artifacts staged, settled READY (a worker run).
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    coordinator = _coordinator(queue, storage, poll_s=0.01)
    summary_id = await coordinator.enqueue_summary(course_id="c1", topic="t", modules=_modules())
    overview_id = await coordinator.enqueue_overview(course_id="c1", brief=_brief())
    for kind, job_id in ((VideoKind.SUMMARY, summary_id), (VideoKind.OVERVIEW, overview_id)):
        job = await queue.get(job_id=job_id, owner_id=_OWNER)
        assert job is not None
        await storage.upload(
            path=VideoArtifactPaths.for_job(job).artifact,
            data=_ready(kind, job_id).model_dump_json(by_alias=True).encode(),
            content_type="application/json",
        )
        await queue.complete(job_id=job_id)

    # Act — the kind→job_id map is exactly what the harness tracks on the draft from the enqueues.
    artifacts = await coordinator.collect_course_videos(
        {VideoKind.SUMMARY: summary_id, VideoKind.OVERVIEW: overview_id}
    )

    # Assert — each kind's finished artifact, provenance tracing its own job.
    assert artifacts[VideoKind.SUMMARY].status is VideoJobStatus.READY
    assert artifacts[VideoKind.SUMMARY].provenance.job_id == summary_id
    assert artifacts[VideoKind.OVERVIEW].status is VideoJobStatus.READY
    assert artifacts[VideoKind.OVERVIEW].provenance.job_id == overview_id


async def test_collect_course_videos_degrades_a_failed_job_to_its_own_kind() -> None:
    # Arrange — the overview job fails (settled FAILED, no artifact); the summary is READY.
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    coordinator = _coordinator(queue, storage, poll_s=0.01)
    summary_id = await coordinator.enqueue_summary(course_id="c1", topic="t", modules=_modules())
    overview_id = await coordinator.enqueue_overview(course_id="c1", brief=_brief())
    summary_job = await queue.get(job_id=summary_id, owner_id=_OWNER)
    assert summary_job is not None
    await storage.upload(
        path=VideoArtifactPaths.for_job(summary_job).artifact,
        data=_ready(VideoKind.SUMMARY, summary_id).model_dump_json(by_alias=True).encode(),
        content_type="application/json",
    )
    await queue.complete(job_id=summary_id)
    await queue.fail(job_id=overview_id, error="boom")

    # Act
    artifacts = await coordinator.collect_course_videos(
        {VideoKind.SUMMARY: summary_id, VideoKind.OVERVIEW: overview_id}
    )

    # Assert — the failed overview degrades to a FAILED artifact carrying the OVERVIEW kind (so the
    # reader shows the overview slot's retry state), never blocking the summary or the publish.
    assert artifacts[VideoKind.SUMMARY].status is VideoJobStatus.READY
    assert artifacts[VideoKind.OVERVIEW].status is VideoJobStatus.FAILED
    assert artifacts[VideoKind.OVERVIEW].kind is VideoKind.OVERVIEW
    assert artifacts[VideoKind.OVERVIEW].provenance is None
