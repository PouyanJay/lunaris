"""CourseStoreLessonSourceProvider tests: a job resolves to its lesson's prose (the four Merrill
segments concatenated), with clean domain failures when the course or lesson is missing."""

import pytest
from lunaris_runtime.schema import (
    Citation,
    Claim,
    Course,
    Lesson,
    MerrillSegments,
    Module,
    Segment,
    VerifierStatus,
    VideoJob,
    VideoKind,
)
from lunaris_video.errors import VideoPipelineError
from lunaris_video.grounding import CourseGroundingPacketBuilder
from lunaris_video.models import PacketKind
from lunaris_video.sourcing import CourseStoreLessonSourceProvider


def _provider(course: Course | None) -> CourseStoreLessonSourceProvider:
    return CourseStoreLessonSourceProvider(
        _FakeCourseStore(course), packet_builder=CourseGroundingPacketBuilder()
    )


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


def _grounded_course() -> Course:
    segments = MerrillSegments(
        activate=Segment(
            prose="Merge sort is a divide-and-conquer sort.",
            claims=[
                Claim(
                    text="Merge sort runs in O(n log n) time.",
                    supported_by="cite-clrs",
                    verifier_status=VerifierStatus.SUPPORTED,
                )
            ],
        ),
        demonstrate=Segment(prose="It splits the array in half repeatedly."),
        apply=Segment(prose="Trace the merge."),
        integrate=Segment(prose="Where else does it help?"),
    )
    lesson = Lesson(id="lesson-1", segments=segments)
    module = Module(id="m1", title="Sorting", competency="sort efficiently", lessons=[lesson])
    return Course(
        id="course-1",
        topic="Algorithms",
        scope_note="for CS undergrads",
        modules=[module],
        provenance=[Citation(id="cite-clrs", title="CLRS")],
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
    provider = _provider(_course())

    # Act
    source = await provider.load(_job())

    # Assert — course topic, module competency as the lesson title, scope as audience, and ALL
    # four segment proses in order.
    assert source.course_topic == "Algorithms"
    assert source.lesson_title == "sort an array efficiently"
    assert source.audience == "for CS undergrads"
    assert "arrays hold ordered elements" in source.prose
    assert "divide-and-conquer" in source.prose


async def test_load_composes_the_grounding_packet_onto_the_source() -> None:
    # Arrange — the lesson carries one SUPPORTED claim grounded by a course citation.
    provider = _provider(_grounded_course())

    # Act
    source = await provider.load(_job())

    # Assert — the GROUND stage hands PLAN a packet, not just prose (cross-cutting principle 2).
    assert source.packet.kind is PacketKind.LESSON
    assert [claim.text for claim in source.packet.claims] == ["Merge sort runs in O(n log n) time."]
    assert source.packet.claims[0].id == "c1"
    assert source.packet.claims[0].source_label == "CLRS"


async def test_a_lesson_with_no_supported_claims_loads_an_empty_packet() -> None:
    # Arrange — prose exists (so the load succeeds) but nothing was verified: framing-only.
    provider = _provider(_course())

    # Act
    source = await provider.load(_job())

    # Assert — a valid load with an empty packet; PLAN must make every scene framing-only.
    assert source.packet.is_empty


async def test_missing_course_is_a_clean_domain_failure() -> None:
    # Arrange
    provider = _provider(None)

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="not found"):
        await provider.load(_job())


async def test_missing_lesson_is_a_clean_domain_failure() -> None:
    # Arrange
    provider = _provider(_course(lesson_id="other"))

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="not found in course"):
        await provider.load(_job(lesson_id="lesson-1"))


async def test_a_lesson_job_without_a_lesson_id_is_rejected() -> None:
    # Arrange
    provider = _provider(_course())

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
    provider = _provider(course)

    # Act / Assert
    with pytest.raises(VideoPipelineError, match="no prose"):
        await provider.load(_job())
