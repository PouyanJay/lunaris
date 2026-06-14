"""Video V7-T4 / §8.6: deleting a course cascades to its video artifacts. Traverses the real
CourseService.delete_course → _purge_course_videos path over the in-memory queue + storage doubles,
asserting the owner's jobs for THAT course (rows + artifacts) are purged while other courses and
other owners are left untouched."""

from pathlib import Path

from lunaris_agent import build_stub_orchestrator
from lunaris_api.service import CourseService
from lunaris_runtime.persistence import (
    CourseStore,
    InMemoryRunStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import VideoJob, VideoKind

_OWNER = "00000000-0000-0000-0000-00000000000a"
_OTHER = "00000000-0000-0000-0000-00000000000b"


def _job(job_id: str, owner: str, course_id: str, *, lesson_id: str | None = None) -> VideoJob:
    kind = VideoKind.LESSON if lesson_id else VideoKind.SUMMARY
    return VideoJob(
        id=job_id,
        user_id=owner,
        course_id=course_id,
        lesson_id=lesson_id,
        kind=kind,
        input_hash="h",
    )


async def _stage(
    queue: InMemoryVideoJobQueue, storage: InMemoryVideoStorage, job: VideoJob
) -> None:
    await queue.enqueue(job)
    paths = VideoArtifactPaths.for_job(job)
    await storage.upload(path=paths.mp4, data=b"x", content_type="video/mp4")
    await storage.upload(path=paths.artifact, data=b"{}", content_type="application/json")


def _service(
    tmp_path: Path, queue: InMemoryVideoJobQueue, storage: InMemoryVideoStorage
) -> CourseService:
    return CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        video_job_queue=queue,
        video_storage=storage,
    )


async def test_delete_course_purges_the_owners_video_jobs_and_artifacts(tmp_path: Path) -> None:
    # Arrange — the owner's c1 has two videos; a second course and another owner's c1 must survive.
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    doomed_summary = _job("d1", _OWNER, "c1")
    doomed_lesson = _job("d2", _OWNER, "c1", lesson_id="l1")
    other_course = _job("k1", _OWNER, "c2")
    other_owner = _job("k2", _OTHER, "c1")
    for job in (doomed_summary, doomed_lesson, other_course, other_owner):
        await _stage(queue, storage, job)
    (tmp_path / "c1.json").write_text("{}")  # the course exists → delete won't 404

    # Act — an owned delete of c1.
    await _service(tmp_path, queue, storage).delete_course("c1", owner_id=_OWNER)

    # Assert — the owner's c1 job rows are gone; the other course + other owner are untouched.
    assert await queue.get(job_id="d1") is None
    assert await queue.get(job_id="d2") is None
    assert await queue.get(job_id="k1") is not None
    assert await queue.get(job_id="k2") is not None

    # And their storage artifacts are gone — NOTHING under either doomed job's prefix survives —
    # while the survivors' artifacts remain.
    paths = storage.paths()
    assert not any(p.startswith(f"{_OWNER}/c1/d1/") for p in paths)
    assert not any(p.startswith(f"{_OWNER}/c1/d2/") for p in paths)
    assert VideoArtifactPaths.for_job(other_course).mp4 in paths
    assert VideoArtifactPaths.for_job(other_owner).mp4 in paths


async def test_unowned_delete_does_not_cascade_videos(tmp_path: Path) -> None:
    # Arrange — auth-off (owner_id=None) can't owner-scope the queue/storage, so the cascade is
    # skipped; the course file still deletes (single-user/no-auth path).
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    await _stage(queue, storage, _job("d1", _OWNER, "c1"))
    (tmp_path / "c1.json").write_text("{}")

    # Act
    await _service(tmp_path, queue, storage).delete_course("c1")

    # Assert — the course file is gone, but the video job is intentionally left (no owner to scope).
    assert not (tmp_path / "c1.json").exists()
    assert await queue.get(job_id="d1") is not None
