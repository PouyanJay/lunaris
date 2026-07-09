"""Full-purge course delete (course-delete T2): deleting a course cascades to the owner's learner
progress. Traverses the real CourseService.delete_course → _purge_course_progress path over the
in-memory progress store, asserting the owner's rows for THAT course (objectives, lessons, and the
course-state row) go while other courses and other owners are left untouched."""

from pathlib import Path

from lunaris_agent import build_stub_orchestrator
from lunaris_api.progress import InMemoryProgressStore
from lunaris_api.service import CourseService
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore

_OWNER = "00000000-0000-0000-0000-00000000000a"
_OTHER = "00000000-0000-0000-0000-00000000000b"


async def _seed(store: InMemoryProgressStore, owner: str | None, course_id: str) -> None:
    await store.set_objective(
        user_id=owner, course_id=course_id, module_id="m1", objective_index=0, understood=True
    )
    await store.set_lesson(user_id=owner, course_id=course_id, lesson_id="l1", state="done")
    await store.touch_course(user_id=owner, course_id=course_id, last_lesson_id="l1")


def _service(tmp_path: Path, progress: InMemoryProgressStore) -> CourseService:
    return CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        progress_store=progress,
    )


async def _has_progress(store: InMemoryProgressStore, owner: str | None, course_id: str) -> bool:
    objectives, lessons = await store.snapshot(user_id=owner, course_id=course_id)
    state = await store.course_state(user_id=owner, course_id=course_id)
    return bool(objectives) or bool(lessons) or state is not None


async def test_delete_course_purges_the_owners_progress(tmp_path: Path) -> None:
    # Arrange — the owner has progress on two courses; another owner shares course c1.
    progress = InMemoryProgressStore()
    await _seed(progress, _OWNER, "c1")
    await _seed(progress, _OWNER, "c2")
    await _seed(progress, _OTHER, "c1")
    (tmp_path / "c1.json").write_text("{}")  # the course exists → delete won't 404

    # Act — an owned delete of c1.
    await _service(tmp_path, progress).delete_course("c1", owner_id=_OWNER)

    # Assert — the owner's c1 progress is gone across all three tables; c2 + other owner remain.
    assert not await _has_progress(progress, _OWNER, "c1")
    assert await _has_progress(progress, _OWNER, "c2")
    assert await _has_progress(progress, _OTHER, "c1")


async def test_unowned_delete_does_not_cascade_progress(tmp_path: Path) -> None:
    # Arrange — auth-off (owner_id=None) can't owner-scope the store, so the progress purge is
    # skipped (mirrors the video cascade's unowned-skip; the Supabase store requires a real user).
    progress = InMemoryProgressStore()
    await _seed(progress, None, "c1")
    (tmp_path / "c1.json").write_text("{}")

    # Act
    await _service(tmp_path, progress).delete_course("c1")

    # Assert — the course file is gone, but the single-user-bucket progress is intentionally left.
    assert not (tmp_path / "c1.json").exists()
    assert await _has_progress(progress, None, "c1")
