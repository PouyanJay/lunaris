from pathlib import Path

from lunaris_runtime.persistence import CourseStore
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
