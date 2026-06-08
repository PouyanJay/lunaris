from pathlib import Path

import pytest
from lunaris_runtime.persistence import CourseStore, OwnerScopedCourseStore
from lunaris_runtime.schema import Course


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    # Arrange
    store = CourseStore(tmp_path / "courses")
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")

    # Act
    store.save(course)
    loaded = store.load("abc")

    # Assert
    assert store.path_for("abc").exists()
    assert loaded == course


def test_saved_file_is_camel_case_json(tmp_path: Path) -> None:
    # Arrange
    store = CourseStore(tmp_path)
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")

    # Act
    store.save(course)
    text = store.path_for("abc").read_text()

    # Assert
    assert '"goalConcept"' in text
    assert '"goal_concept"' not in text


class _RecordingCourseStore:
    """Captures the owner_id each call receives, so the decorator's binding can be asserted."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def save(self, course: Course, *, owner_id: str | None = None) -> None:
        self.calls.append(("save", owner_id))

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        self.calls.append(("load", owner_id))
        return Course(id=course_id, topic="t", goal_concept="kc-1")

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        self.calls.append(("delete", owner_id))
        return True


def test_owner_scoped_store_binds_the_owner_on_every_call() -> None:
    # Arrange — the harness calls a plain save(course); the decorator must inject the bound owner so
    # the underlying store stamps user_id without owner_id threading into the agent.
    inner = _RecordingCourseStore()
    scoped = OwnerScopedCourseStore(inner, "user-7")
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")

    # Act — call each method the way the pipeline does (no owner_id passed).
    scoped.save(course)
    scoped.load("abc")
    scoped.delete("abc")

    # Assert — every call reached the inner store carrying the bound owner.
    assert inner.calls == [("save", "user-7"), ("load", "user-7"), ("delete", "user-7")]


def test_owner_scoped_store_rejects_a_conflicting_owner() -> None:
    # Arrange — the bound identity is the single source of truth.
    inner = _RecordingCourseStore()
    scoped = OwnerScopedCourseStore(inner, "user-7")

    # Act / Assert — a different explicit owner is a bug (two sources of truth), so it raises loudly
    # rather than silently overriding — and nothing reaches the inner store.
    with pytest.raises(ValueError, match="bound to one owner"):
        scoped.save(Course(id="abc", topic="t", goal_concept="kc-1"), owner_id="someone-else")
    assert inner.calls == []


def test_owner_scoped_store_allows_the_matching_owner() -> None:
    # Arrange — passing the SAME owner the decorator is bound to is harmless (no conflict).
    inner = _RecordingCourseStore()
    scoped = OwnerScopedCourseStore(inner, "user-7")

    # Act
    scoped.save(Course(id="abc", topic="t", goal_concept="kc-1"), owner_id="user-7")

    # Assert
    assert inner.calls == [("save", "user-7")]
