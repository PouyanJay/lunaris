"""Orchestrator.regenerate_lesson — re-author one lesson of an existing course in place."""

from pathlib import Path

from lunaris_agent import build_stub_orchestrator
from lunaris_runtime.persistence import CourseStore


async def test_regenerate_lesson_reauthors_illustrates_and_persists(tmp_path: Path) -> None:
    # Arrange — build a course, then target its first lesson.
    store = CourseStore(tmp_path)
    orchestrator = build_stub_orchestrator(store)
    course = await orchestrator.run("binary search", course_id="c1", run_id="r1")
    lesson_id = course.modules[0].lessons[0].id

    # Act
    updated = await orchestrator.regenerate_lesson("c1", lesson_id, run_id="r2")

    # Assert — the lesson is back, re-illustrated with a branded spec, and persisted to the store.
    assert updated is not None
    lesson = next(
        lesson for module in updated.modules for lesson in module.lessons if lesson.id == lesson_id
    )
    assert lesson.segments.demonstrate.visuals
    assert lesson.segments.demonstrate.visuals[0].spec is not None
    # Persisted to disk (not just mutated in memory): the reloaded lesson carries the new visual.
    reloaded = store.load("c1").modules[0].lessons[0]
    assert reloaded.id == lesson_id
    assert reloaded.segments.demonstrate.visuals


async def test_regenerate_lesson_returns_none_for_unknown_lesson_or_course(tmp_path: Path) -> None:
    # Arrange
    store = CourseStore(tmp_path)
    orchestrator = build_stub_orchestrator(store)
    await orchestrator.run("binary search", course_id="c1", run_id="r1")

    # Act / Assert — an unknown lesson and an unknown course both yield None (→ 404 at the API).
    assert await orchestrator.regenerate_lesson("c1", "ghost", run_id="r2") is None
    assert await orchestrator.regenerate_lesson("missing", "any", run_id="r2") is None
