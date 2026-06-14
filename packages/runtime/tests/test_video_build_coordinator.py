"""Video V4-T0: the build's video-enqueue coordinator (``QueueVideoBuildCoordinator``).

Enqueues one lesson-video job per cleared module onto the shared queue, deduping within a build so a
lesson enqueues exactly once across revise rounds, and never lets a queue hiccup break the build.
"""

from lunaris_runtime.persistence import InMemoryVideoJobQueue, PersistenceError
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind
from lunaris_runtime.video_build import QueueVideoBuildCoordinator, video_input_hash

_OWNER = "user-a"


async def test_enqueue_lesson_creates_a_queued_lesson_job() -> None:
    # Arrange
    queue = InMemoryVideoJobQueue()
    coordinator = QueueVideoBuildCoordinator(queue=queue, owner_id=_OWNER, config={"voice": True})

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
    coordinator = QueueVideoBuildCoordinator(queue=queue, owner_id=_OWNER)

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
    coordinator = QueueVideoBuildCoordinator(queue=_FailingQueue(), owner_id=_OWNER)

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


class _FailingQueue:
    """A queue double whose enqueue always raises — to prove enqueue is best-effort."""

    async def enqueue(self, job: VideoJob) -> None:
        raise PersistenceError("queue down")

    async def claim(self, *, worker_id: str) -> VideoJob | None:
        return None

    async def heartbeat(self, *, job_id: str) -> None: ...

    async def complete(self, *, job_id: str) -> None: ...

    async def fail(self, *, job_id: str, error: str) -> None: ...

    async def get(self, *, job_id: str, owner_id: str | None = None) -> VideoJob | None:
        return None
