"""Video V4: the build's video coordinator (``QueueVideoBuildCoordinator``).

T0 — enqueues one lesson-video job per cleared module onto the shared queue, deduping within a
build so a lesson enqueues exactly once across revise rounds, never letting a queue hiccup break it.
T1 — ``collect`` awaits the enqueued jobs at finalize and folds each finished artifact into its
lesson, degrading on failure (a FAILED / unreadable / timed-out job → a FAILED retry-state one).
"""

from lunaris_runtime.persistence import (
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
    PersistenceError,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import (
    VideoArtifact,
    VideoJob,
    VideoJobStatus,
    VideoKind,
    VideoProvenance,
)
from lunaris_runtime.video_build import QueueVideoBuildCoordinator, video_input_hash

_OWNER = "user-a"


def _coordinator(
    queue: object, storage: object | None = None, **kwargs: object
) -> QueueVideoBuildCoordinator:
    return QueueVideoBuildCoordinator(
        queue=queue, storage=storage or InMemoryVideoStorage(), owner_id=_OWNER, **kwargs
    )


def _ready_artifact(job_id: str, *, duration_s: float = 72.0) -> VideoArtifact:
    return VideoArtifact(
        kind=VideoKind.LESSON,
        status=VideoJobStatus.READY,
        provenance=VideoProvenance(
            job_id=job_id,
            course_id="c1",
            lesson_id="m0-l0",
            kind=VideoKind.LESSON,
            model="stub",
            contract_hash="h",
            input_hash="h",
            claim_ids=["c1"],
            generated_at="2026-01-01T00:00:00+00:00",
        ),
        narrated=False,
        duration_s=duration_s,
    )


async def _stage_ready(
    coordinator: QueueVideoBuildCoordinator,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    artifact: VideoArtifact,
) -> str:
    """Enqueue a lesson, stage its artifact.json, settle it READY — what a worker run produces."""
    job_id = await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")
    assert job_id is not None
    job = await queue.get(job_id=job_id, owner_id=_OWNER)
    assert job is not None
    await storage.upload(
        path=VideoArtifactPaths.for_job(job).artifact,
        data=artifact.model_dump_json(by_alias=True).encode(),
        content_type="application/json",
    )
    await queue.complete(job_id=job_id)
    return job_id


# ── T0: enqueue ─────────────────────────────────────────────────────────────────────


async def test_enqueue_lesson_creates_a_queued_lesson_job() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    coordinator = _coordinator(queue, config={"voice": True})

    # Act
    job_id = await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")

    # Assert — a QUEUED lesson job owned by the build's owner, with the config snapshot stamped on.
    assert job_id is not None
    job = await queue.get(job_id=job_id, owner_id=_OWNER)
    assert job is not None
    assert job.kind is VideoKind.LESSON
    assert job.course_id == "c1"
    assert job.lesson_id == "m0-l0"
    assert job.user_id == _OWNER
    assert job.status is VideoJobStatus.QUEUED
    assert job.config == {"voice": True}
    assert job.input_hash == video_input_hash("c1", "m0-l0")


async def test_enqueue_lesson_is_idempotent_within_a_build() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    coordinator = _coordinator(queue)

    # Act — the same lesson twice (a re-verify of an already-clean module).
    first = await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")
    second = await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")

    # Assert — one job id, and only one row claimable from the queue.
    assert first == second
    claimed = await queue.claim(worker_id="w")
    assert claimed is not None and claimed.id == first
    assert await queue.claim(worker_id="w") is None


async def test_enqueue_failure_degrades_to_none_never_raises() -> None:
    # Arrange — a queue whose enqueue always fails (an infrastructure hiccup).
    coordinator = _coordinator(_FailingQueue())

    # Act — must not raise: a video must never break the build (plan §0 failure policy).
    job_id = await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")

    # Assert — degrades to no job for that lesson.
    assert job_id is None


def test_video_input_hash_is_stable_and_coordinate_keyed() -> None:
    # The build coordinator and the on-demand endpoint must hash the same lesson identically, and
    # distinguish both the lesson AND the course (find_active dedup is course-scoped).
    assert video_input_hash("c1", "m0-l0") == video_input_hash("c1", "m0-l0")
    assert video_input_hash("c1", "m0-l0") != video_input_hash("c1", "m0-l1")
    assert video_input_hash("c1", "m0-l0") != video_input_hash("c2", "m0-l0")


# ── T1: collect (await + degrade) ────────────────────────────────────────────────────


async def test_collect_returns_a_ready_artifact_for_a_completed_job() -> None:
    # Arrange — a job that finished READY with its artifact.json staged (a worker run's output).
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    coordinator = _coordinator(queue, storage, poll_s=0.01)
    job_id = await _stage_ready(
        coordinator, queue, storage, _ready_artifact("job", duration_s=60.0)
    )

    # Act
    result = await coordinator.collect({"m0-l0": job_id})

    # Assert — the finished artifact reaches the lesson, provenance + playback metadata intact.
    artifact = result["m0-l0"]
    assert artifact.status is VideoJobStatus.READY
    assert artifact.provenance is not None
    assert artifact.provenance.job_id == "job"
    assert artifact.duration_s == 60.0


async def test_collect_degrades_a_failed_job_to_a_retry_state_artifact() -> None:
    # Arrange — an enqueued job the worker settled FAILED.
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    coordinator = _coordinator(queue, storage, poll_s=0.01)
    job_id = await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")
    await queue.fail(job_id=job_id, error="render exploded")

    # Act
    result = await coordinator.collect({"m0-l0": job_id})

    # Assert — a FAILED retry-state artifact (no provenance), never a raised error.
    artifact = result["m0-l0"]
    assert artifact.status is VideoJobStatus.FAILED
    assert artifact.provenance is None


async def test_collect_degrades_a_job_still_running_past_the_timeout() -> None:
    # Arrange — a job that never leaves QUEUED, and a tiny await budget.
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    coordinator = _coordinator(queue, storage, await_timeout_s=0.05, poll_s=0.01)
    job_id = await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")

    # Act — the blocking await is bounded; a stuck job degrades rather than hanging the build.
    result = await coordinator.collect({"m0-l0": job_id})

    # Assert
    assert result["m0-l0"].status is VideoJobStatus.FAILED


async def test_collect_degrades_when_the_ready_artifact_is_unreadable() -> None:
    # Arrange — a READY job whose artifact.json never landed (a storage gap).
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    coordinator = _coordinator(queue, storage, poll_s=0.01)
    job_id = await coordinator.enqueue_lesson(course_id="c1", lesson_id="m0-l0")
    await queue.complete(job_id=job_id)  # READY but no artifact staged

    # Act
    result = await coordinator.collect({"m0-l0": job_id})

    # Assert — degrades to the retry state rather than a half-stitched payload.
    assert result["m0-l0"].status is VideoJobStatus.FAILED


async def test_collect_handles_many_jobs_concurrently() -> None:
    # Arrange — three lessons, all READY.
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    coordinator = _coordinator(queue, storage, poll_s=0.01)
    jobs: dict[str, str] = {}
    for n in range(3):
        lesson = f"m{n}-l0"
        job_id = await coordinator.enqueue_lesson(course_id="c1", lesson_id=lesson)
        job = await queue.get(job_id=job_id, owner_id=_OWNER)
        await storage.upload(
            path=VideoArtifactPaths.for_job(job).artifact,
            data=_ready_artifact(job_id).model_dump_json(by_alias=True).encode(),
            content_type="application/json",
        )
        await queue.complete(job_id=job_id)
        jobs[lesson] = job_id

    # Act
    result = await coordinator.collect(jobs)

    # Assert — every lesson collected, all READY.
    assert set(result) == set(jobs)
    assert all(artifact.status is VideoJobStatus.READY for artifact in result.values())


class _FailingQueue:
    """A queue double whose enqueue always raises — to prove enqueue is best-effort."""

    async def enqueue(self, job: VideoJob) -> None:
        raise PersistenceError("queue down")

    async def claim(self, *, worker_id: str) -> VideoJob | None:
        return None

    async def heartbeat(self, *, job_id: str) -> None: ...

    async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None: ...

    async def fail(self, *, job_id: str, error: str) -> None: ...

    async def get(self, *, job_id: str, owner_id: str | None = None) -> VideoJob | None:
        return None

    async def find_active(
        self, *, course_id: str, lesson_id: str | None, kind: VideoKind, owner_id: str
    ) -> VideoJob | None:
        return None
