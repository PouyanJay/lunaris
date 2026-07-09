"""Full-purge course delete (course-delete T3): deleting a course cascades to the owner's bookmarks
and per-course activity feed. Traverses the real CourseService.delete_course path over the in-memory
bookmark + activity stores, asserting the owner's rows for THAT course go while other courses and
owners survive. study_minutes has no course dimension, so global study time is intentionally left
untouched (AD2)."""

from datetime import UTC, datetime
from pathlib import Path

from lunaris_agent import build_stub_orchestrator
from lunaris_api.activity import InMemoryActivityStore, LearningEvent
from lunaris_api.bookmarks import Bookmark, InMemoryBookmarkStore
from lunaris_api.service import CourseService
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore

_OWNER = "00000000-0000-0000-0000-00000000000a"
_OTHER = "00000000-0000-0000-0000-00000000000b"
_WHEN = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def _bookmark(course_id: str) -> Bookmark:
    return Bookmark(
        kind="lesson",
        course_id=course_id,
        target_id="l1",
        course_title="C",
        title="L1",
        lesson_id="l1",
        snippet=None,
        concept_tier=None,
        trust_tier=None,
        credibility=None,
        note=None,
        saved_at=_WHEN,
    )


def _event(course_id: str) -> LearningEvent:
    return LearningEvent(
        event_type="completed",
        course_id=course_id,
        course_title="C",
        lesson_id="l1",
        lesson_title="L1",
        kc_id=None,
        kc_label=None,
        occurred_at=_WHEN,
    )


async def _seed(
    bookmarks: InMemoryBookmarkStore,
    activity: InMemoryActivityStore,
    owner: str | None,
    course_id: str,
) -> None:
    await bookmarks.save(user_id=owner, bookmark=_bookmark(course_id))
    await activity.record_event(user_id=owner, event=_event(course_id))


def _service(
    tmp_path: Path, bookmarks: InMemoryBookmarkStore, activity: InMemoryActivityStore
) -> CourseService:
    return CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        bookmark_store=bookmarks,
        activity_store=activity,
    )


async def test_delete_course_purges_owner_bookmarks_and_activity(tmp_path: Path) -> None:
    # Arrange — the owner has saves + events on two courses; another owner shares c1; plus a global
    # study-minute bucket (no course dimension).
    bookmarks, activity = InMemoryBookmarkStore(), InMemoryActivityStore()
    await _seed(bookmarks, activity, _OWNER, "c1")
    await _seed(bookmarks, activity, _OWNER, "c2")
    await _seed(bookmarks, activity, _OTHER, "c1")
    await activity.record_minute(user_id=_OWNER, bucket_start=_WHEN)
    (tmp_path / "c1.json").write_text("{}")

    # Act
    await _service(tmp_path, bookmarks, activity).delete_course("c1", owner_id=_OWNER)

    # Assert — the owner's c1 bookmarks + feed events are gone; c2 and the other owner survive.
    assert {b.course_id for b in await bookmarks.list(user_id=_OWNER)} == {"c2"}
    assert {e.course_id for e in await activity.events(user_id=_OWNER)} == {"c2"}
    assert {b.course_id for b in await bookmarks.list(user_id=_OTHER)} == {"c1"}
    assert {e.course_id for e in await activity.events(user_id=_OTHER)} == {"c1"}
    # study_minutes has no course dimension → global study time is intentionally untouched (AD2).
    assert await activity.minutes(user_id=_OWNER) == [_WHEN]


async def test_unowned_delete_does_not_cascade_learner_data(tmp_path: Path) -> None:
    # Arrange — auth-off (owner_id=None) can't owner-scope the stores, so the purge is skipped.
    bookmarks, activity = InMemoryBookmarkStore(), InMemoryActivityStore()
    await _seed(bookmarks, activity, None, "c1")
    (tmp_path / "c1.json").write_text("{}")

    # Act
    await _service(tmp_path, bookmarks, activity).delete_course("c1")

    # Assert — the course file is gone, but the single-user-bucket learner data is left.
    assert not (tmp_path / "c1.json").exists()
    assert {b.course_id for b in await bookmarks.list(user_id=None)} == {"c1"}
    assert {e.course_id for e in await activity.events(user_id=None)} == {"c1"}
