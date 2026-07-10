"""course-cover-images T1: deleting a course cascades to its cover image. Traverses the real
CourseService.delete_course → _purge_course_covers path over the in-memory cover queue + storage
doubles, asserting the owner's cover for THAT course (row + image + provenance artifacts) is purged
while other courses and other owners are left untouched."""

from pathlib import Path

from lunaris_agent import build_stub_orchestrator
from lunaris_api.service import CourseService
from lunaris_runtime.persistence import (
    CourseStore,
    CoverArtifactPaths,
    InMemoryCoverJobQueue,
    InMemoryCoverStorage,
    InMemoryRunStore,
)
from lunaris_runtime.schema import CoverJob

_OWNER = "00000000-0000-0000-0000-00000000000a"
_OTHER = "00000000-0000-0000-0000-00000000000b"


def _job(job_id: str, owner: str, course_id: str) -> CoverJob:
    return CoverJob(id=job_id, user_id=owner, course_id=course_id, input_hash="h")


async def _stage(
    queue: InMemoryCoverJobQueue, storage: InMemoryCoverStorage, job: CoverJob
) -> None:
    await queue.enqueue(job)
    paths = CoverArtifactPaths.for_job(job)
    await storage.upload(path=paths.image, data=b"png", content_type="image/png")
    await storage.upload(path=paths.provenance, data=b"{}", content_type="application/json")


def _service(
    tmp_path: Path, queue: InMemoryCoverJobQueue, storage: InMemoryCoverStorage
) -> CourseService:
    return CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        cover_job_queue=queue,
        cover_storage=storage,
    )


async def test_delete_course_purges_the_owners_cover_job_and_image(tmp_path: Path) -> None:
    # Arrange — the owner's c1 has a cover; a second course and another owner's c1 must survive.
    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    doomed = _job("d1", _OWNER, "c1")
    other_course = _job("k1", _OWNER, "c2")
    other_owner = _job("k2", _OTHER, "c1")
    for job in (doomed, other_course, other_owner):
        await _stage(queue, storage, job)
    (tmp_path / "c1.json").write_text("{}")  # the course exists → delete won't 404

    # Act — an owned delete of c1.
    await _service(tmp_path, queue, storage).delete_course("c1", owner_id=_OWNER)

    # Assert — the owner's c1 cover row is gone; the other course + other owner are untouched.
    assert await queue.get(job_id="d1") is None
    assert await queue.get(job_id="k1") is not None
    assert await queue.get(job_id="k2") is not None

    # And the doomed cover's storage artifacts are gone, while the survivors' remain.
    paths = storage.paths()
    assert not any(p.startswith(f"{_OWNER}/c1/d1/") for p in paths)
    assert CoverArtifactPaths.for_job(other_course).image in paths
    assert CoverArtifactPaths.for_job(other_owner).image in paths


async def test_unowned_delete_does_not_cascade_covers(tmp_path: Path) -> None:
    # Arrange — auth-off (owner_id=None) can't owner-scope the queue/storage, so the cascade is
    # skipped; the course file still deletes (single-user/no-auth path).
    queue, storage = InMemoryCoverJobQueue(), InMemoryCoverStorage()
    await _stage(queue, storage, _job("d1", _OWNER, "c1"))
    (tmp_path / "c1.json").write_text("{}")

    # Act
    await _service(tmp_path, queue, storage).delete_course("c1")

    # Assert — the course file is gone, but the cover job is intentionally left (no owner to scope).
    assert not (tmp_path / "c1.json").exists()
    assert await queue.get(job_id="d1") is not None
