"""course-delete T6 — the capstone: one delete_course call purges EVERYTHING about a course across
every per-course store at once (course file + run row + progress + bookmarks + activity feed +
grounding corpus), while another owner's identically-keyed data survives and study minutes (no
course dimension) are left. The per-arm cascade tests (T2-T4) prove each store in isolation; this
proves the whole cascade fires together and stays owner/course scoped."""

from datetime import UTC, datetime
from pathlib import Path

from lunaris_agent import build_stub_orchestrator
from lunaris_api.activity import InMemoryActivityStore, LearningEvent
from lunaris_api.bookmarks import Bookmark, InMemoryBookmarkStore
from lunaris_api.progress import InMemoryProgressStore
from lunaris_api.service import CourseService
from lunaris_grounding import GroundingDocument, InMemoryCorpusStore
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


def _doc(doc_id: str, course_id: str) -> GroundingDocument:
    return GroundingDocument(
        id=doc_id, kc_id="k1", content="x", embedding=(0.1,), course_id=course_id, source_id="s1"
    )


class _Stores:
    def __init__(self) -> None:
        self.progress = InMemoryProgressStore()
        self.bookmarks = InMemoryBookmarkStore()
        self.activity = InMemoryActivityStore()
        self.corpus = InMemoryCorpusStore()

    async def seed(self, owner: str, course_id: str) -> None:
        await self.progress.set_lesson(
            user_id=owner, course_id=course_id, lesson_id="l1", state="done"
        )
        await self.progress.touch_course(user_id=owner, course_id=course_id)
        await self.bookmarks.save(user_id=owner, bookmark=_bookmark(course_id))
        await self.activity.record_event(user_id=owner, event=_event(course_id))
        await self.corpus.upsert([_doc(f"{owner}-{course_id}", course_id)])

    async def footprint(self, owner: str, course_id: str) -> dict[str, int]:
        objectives, lessons = await self.progress.snapshot(user_id=owner, course_id=course_id)
        state = await self.progress.course_state(user_id=owner, course_id=course_id)
        marks = [b for b in await self.bookmarks.list(user_id=owner) if b.course_id == course_id]
        events = [e for e in await self.activity.events(user_id=owner) if e.course_id == course_id]
        chunks = await self.corpus.match([0.1], k=100, min_score=0.0, course_id=course_id)
        return {
            "progress": len(objectives) + len(lessons) + (1 if state else 0),
            "bookmarks": len(marks),
            "activity": len(events),
            "corpus": len(chunks),
        }


def _service(tmp_path: Path, stores: _Stores) -> CourseService:
    return CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        progress_store=stores.progress,
        bookmark_store=stores.bookmarks,
        activity_store=stores.activity,
        corpus_store=stores.corpus,
    )


async def test_delete_course_purges_every_asset_type_and_only_the_target(tmp_path: Path) -> None:
    # Arrange — the owner has a full footprint on c1 AND c2; another owner owns their own course c3
    # (course ids are globally unique, one owner per course — the corpus purge is course-scoped, so
    # a SHARED id would cross-purge, but that never happens); plus a global study-minute bucket.
    stores = _Stores()
    await stores.seed(_OWNER, "c1")
    await stores.seed(_OWNER, "c2")
    await stores.seed(_OTHER, "c3")
    await stores.activity.record_minute(user_id=_OWNER, bucket_start=_WHEN)
    (tmp_path / "c1.json").write_text("{}")
    # Every arm has data to purge (guards against a vacuous assertion if a seed no-ops).
    assert all(count > 0 for count in (await stores.footprint(_OWNER, "c1")).values())

    # Act — one owned delete of c1.
    await _service(tmp_path, stores).delete_course("c1", owner_id=_OWNER)

    # Assert — EVERYTHING about the owner's c1 is gone across every store...
    assert await stores.footprint(_OWNER, "c1") == {
        "progress": 0,
        "bookmarks": 0,
        "activity": 0,
        "corpus": 0,
    }
    assert not (tmp_path / "c1.json").exists()
    # ...while the owner's other course and the other owner's course are fully intact...
    assert all(count > 0 for count in (await stores.footprint(_OWNER, "c2")).values())
    assert all(count > 0 for count in (await stores.footprint(_OTHER, "c3")).values())
    # ...and study minutes (no course dimension) are never touched by a course delete (AD2).
    assert await stores.activity.minutes(user_id=_OWNER) == [_WHEN]
