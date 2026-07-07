"""Unit coverage for the library-card derivation — the level buckets and learner-status rules
the integration suite can't pin precisely (the stub pipeline's difficulties are fixed)."""

from datetime import UTC, datetime

import pytest
from lunaris_api.library import CourseMarks, LibraryEntry, derive_course_summary
from lunaris_api.progress import ObjectiveMark
from lunaris_runtime.schema import (
    Course,
    CourseRun,
    KnowledgeComponent,
    PrerequisiteGraph,
    RunStatus,
)

_NOW = datetime(2026, 7, 7, tzinfo=UTC)


def _entry(difficulties: list[float]) -> LibraryEntry:
    nodes = [
        KnowledgeComponent(
            id=f"kc-{index}",
            label=f"KC {index}",
            definition="",
            difficulty=difficulty,
            bloom_ceiling="understand",
        )
        for index, difficulty in enumerate(difficulties)
    ]
    course = Course(id="course-1", topic="t", graph=PrerequisiteGraph(nodes=nodes))
    run = CourseRun(
        id="course-1",
        run_id="run-1",
        topic="t",
        status=RunStatus.COMPLETED,
        created_at=_NOW,
        updated_at=_NOW,
    )
    return LibraryEntry(run=run, course=course)


@pytest.mark.parametrize(
    ("difficulties", "expected"),
    [
        ([0.0, 0.2], "beginner"),
        ([0.33], "beginner"),
        ([0.34], "intermediate"),  # lower boundary is inclusive to intermediate
        ([0.2, 0.8], "intermediate"),  # mean 0.5
        ([0.66], "intermediate"),
        ([0.67], "advanced"),  # upper boundary is inclusive to advanced
        ([0.9, 1.0], "advanced"),
    ],
    ids=[
        "mean_0.1_beginner",
        "just_below_floor_0.33_beginner",
        "floor_0.34_intermediate",
        "mean_0.5_intermediate",
        "just_below_ceiling_0.66_intermediate",
        "ceiling_0.67_advanced",
        "mean_0.95_advanced",
    ],
)
def test_level_buckets_mean_kc_difficulty(difficulties: list[float], expected: str) -> None:
    # Act
    summary = derive_course_summary(_entry(difficulties), CourseMarks())

    # Assert
    assert summary.level == expected
    assert summary.concept_total == len(difficulties)


def test_level_is_none_without_mapped_concepts() -> None:
    # Act — a degenerate course whose graph never mapped (no invented level).
    summary = derive_course_summary(_entry([]), CourseMarks())

    # Assert
    assert summary.level is None
    assert summary.concept_total == 0


def test_zero_lesson_course_with_marks_reads_in_progress_not_completed() -> None:
    # Arrange — objectives understood but no lessons exist: percent stays 0, yet the learner
    # HAS touched the course, so it must read in_progress (never completed on 0/0 lessons).
    mark = ObjectiveMark(
        course_id="course-1", module_id="m-1", objective_index=0, understood_at=_NOW
    )

    # Act
    summary = derive_course_summary(_entry([0.5]), CourseMarks(objectives=[mark]))

    # Assert
    assert summary.learner_status == "in_progress"
    assert summary.percent == 0


def test_zero_lesson_course_without_marks_reads_not_started() -> None:
    # Act
    summary = derive_course_summary(_entry([0.5]), CourseMarks())

    # Assert
    assert summary.learner_status == "not_started"
    assert summary.lesson_total == 0
