from pathlib import Path

from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import Course


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    # Arrange
    store = CourseStore(tmp_path / "courses")
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")

    # Act
    saved_path = store.save(course)
    loaded = store.load("abc")

    # Assert
    assert saved_path.exists()
    assert loaded == course


def test_saved_file_is_camel_case_json(tmp_path: Path) -> None:
    # Arrange
    store = CourseStore(tmp_path)
    course = Course(id="abc", topic="graphs", goal_concept="kc-9")

    # Act
    text = store.save(course).read_text()

    # Assert
    assert '"goalConcept"' in text
    assert '"goal_concept"' not in text
