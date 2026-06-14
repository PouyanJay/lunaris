"""Course.videos (video V5-T0): the course-level videos — a SUMMARY trailer and an OVERVIEW intro —
ride at the top of the course payload in a ``CourseVideos`` block, the course analogue of
``Lesson.video``. Defined now (populated by the build in V5-T2) so the payload shape is stable and a
course's two opening videos have a home, with provenance traversing pipeline → payload → API."""

from lunaris_runtime.schema import (
    Course,
    CourseVideos,
    Module,
    VideoArtifact,
    VideoJobStatus,
    VideoKind,
    VideoProvenance,
)


def _artifact(kind: VideoKind) -> VideoArtifact:
    return VideoArtifact(
        kind=kind,
        status=VideoJobStatus.READY,
        provenance=VideoProvenance(
            job_id=f"job-{kind.value}",
            course_id="course-1",
            lesson_id=None,  # course-level kinds carry no lesson
            kind=kind,
            model="claude-opus-4-8",
            contract_hash="abc123",
            input_hash="def456",
            claim_ids=["c1", "c2"],
            generated_at="2026-06-13T10:00:00+00:00",
        ),
        narrated=False,
        duration_s=78.0,
    )


def test_course_carries_both_course_level_videos_in_the_payload() -> None:
    # Arrange — a course with a SUMMARY trailer and an OVERVIEW intro, the V5 Overview section.
    course = Course(
        id="course-1",
        topic="Algorithms",
        modules=[Module(id="m1", title="Sorting")],
        videos=CourseVideos(
            summary=_artifact(VideoKind.SUMMARY),
            overview=_artifact(VideoKind.OVERVIEW),
        ),
    )

    # Act — round-trip the whole course payload (camelCase wire, like every CourseModel).
    restored = Course.model_validate_json(course.model_dump_json(by_alias=True))

    # Assert — both course-level videos survived the traversal, each with its provenance and kind.
    assert restored.videos is not None
    assert restored.videos.summary is not None
    assert restored.videos.summary.kind is VideoKind.SUMMARY
    assert restored.videos.summary.provenance.lesson_id is None
    assert restored.videos.overview is not None
    assert restored.videos.overview.kind is VideoKind.OVERVIEW
    assert restored.videos.overview.provenance.contract_hash == "abc123"


def test_course_videos_serializes_as_a_nested_block_with_null_for_an_unbuilt_kind() -> None:
    # Arrange / Act — the wire carries a ``videos`` block; summary/overview are nested artifacts and
    # an unbuilt kind is explicit null (not omitted), so the reader reads one stable slice.
    course = Course(
        id="course-1",
        topic="Algorithms",
        videos=CourseVideos(summary=_artifact(VideoKind.SUMMARY)),
    )
    wire = course.model_dump(by_alias=True)

    # Assert — the reader reads course.videos.summary; an unbuilt overview is absent (None).
    assert wire["videos"]["summary"]["kind"] == "summary"
    assert wire["videos"]["overview"] is None


def test_a_course_without_course_level_videos_defaults_to_none() -> None:
    # Arrange / Act — a course built before V5 (or with video off) carries no Overview section.
    course = Course(id="course-1", topic="Algorithms")

    # Assert — backward compatible: the field is optional and absent by default.
    assert course.videos is None
    restored = Course.model_validate_json(course.model_dump_json(by_alias=True))
    assert restored.videos is None
