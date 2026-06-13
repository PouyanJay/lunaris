"""CourseStoreLessonSourceProvider tests: a job resolves to its lesson's prose (the four Merrill
segments concatenated), with clean domain failures when the course or lesson is missing."""

import pytest
from lunaris_runtime.schema import (
    Course,
    Lesson,
    MerrillSegments,
    Module,
    Segment,
    VideoJob,
    VideoKind,
)
from lunaris_video.errors import VideoPipelineError
from lunaris_video.sourcing import CourseStoreLessonSourceProvider


class _FakeCourseStore:
    def __init__(self, course: Course | None) -> None:
        self._course = course

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        if self._course is None or self._course.id != course_id:
            raise FileNotFoundError(course_id)
        return self._course

    def save(self, course: Course, *, owner_id: str | None = None) -> None: ...

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return False


def _segments() -> MerrillSegments:
    return MerrillSegments(
        activate=Segment(prose="Recall that arrays hold ordered elements."),
        demonstrate=Segment(prose="Merge sort splits the array in half."),
        apply=Segment(prose="Trace the merge of [3,1] and [2,4]."),
        integrate=Segment(prose="Where else does divide-and-conquer apply?"),
    )


def _course(*, lesson_id: str = "lesson-1") -> Course:
    lesson = Lesson(id=lesson_id, segments=_segments())
    module = Module(
        id="m1", title="Sorting", competency="sort an array efficiently", lessons=[lesson]
    )
    return Course(
        id="course-1", topic="Algorithms", scope_note="for CS undergrads", modules=[module]
    )


def _job(*, lesson_id: str | None = "lesson-1") -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id=lesson_id,
        kind=VideoKind.LESSON,
        input_hash="h",
    )


async def test_load_flattens_the_lesson_into_a_source() -> None:
    # Arrange
    provider = CourseStoreLessonSourceProvider(_FakeCourseStore(_course()))

    # Act
    source = await provider.load(_job())

    # Assert — course topic, module competency as the lesson title, scope as audience, and ALL
    # four segment proses in order.
    assert source.course_topic == "Algorithms"
    assert source.lesson_title == "sort an array efficiently"
    assert source.audience == "for CS undergrads"
    assert "arrays hold ordered elements" in source.prose
    assert "divide-and-conquer" in source.prose


async def test_missing_course_is_a_clean_domain_failure() -> None:
    # Arrange
    provider = CourseStoreLessonSourceProvider(_FakeCourseStore(None))

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="not found"):
        await provider.load(_job())


async def test_missing_lesson_is_a_clean_domain_failure() -> None:
    # Arrange
    provider = CourseStoreLessonSourceProvider(_FakeCourseStore(_course(lesson_id="other")))

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="not found in course"):
        await provider.load(_job(lesson_id="lesson-1"))


async def test_a_lesson_job_without_a_lesson_id_is_rejected() -> None:
    # Arrange
    provider = CourseStoreLessonSourceProvider(_FakeCourseStore(_course()))

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="no lesson_id"):
        await provider.load(_job(lesson_id=None))


async def test_a_lesson_with_only_blank_prose_is_rejected() -> None:
    # Arrange — a lesson whose four segments are all empty: nothing to ground a video on.
    blank = MerrillSegments(
        activate=Segment(), demonstrate=Segment(), apply=Segment(), integrate=Segment()
    )
    lesson = Lesson(id="lesson-1", segments=blank)
    module = Module(id="m1", title="Sorting", lessons=[lesson])
    course = Course(id="course-1", topic="Algorithms", modules=[module])
    provider = CourseStoreLessonSourceProvider(_FakeCourseStore(course))

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="no prose"):
        await provider.load(_job())
