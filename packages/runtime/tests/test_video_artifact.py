"""VideoArtifact / VideoProvenance schemas (video V2-T3): the wire shape a finished video rides in
the course payload, carrying the grounding provenance the CLAUDE.md contract requires — claim ids,
contract/input hashes, model, job id, timestamp. Defined now (populated by the build in V4) so the
payload shape is stable and provenance traverses pipeline → payload → API."""

from lunaris_runtime.schema import (
    Course,
    Lesson,
    MerrillSegments,
    Module,
    Segment,
    VideoArtifact,
    VideoJobStatus,
    VideoKind,
    VideoProvenance,
)


def _provenance() -> VideoProvenance:
    return VideoProvenance(
        job_id="job-1",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        model="claude-opus-4-8",
        contract_hash="abc123",
        input_hash="def456",
        claim_ids=["c1", "c3"],
        generated_at="2026-06-13T10:00:00+00:00",
    )


def _artifact() -> VideoArtifact:
    return VideoArtifact(
        kind=VideoKind.LESSON,
        status=VideoJobStatus.READY,
        provenance=_provenance(),
        narrated=False,
        duration_s=72.0,
    )


def test_provenance_round_trips_through_json() -> None:
    # Arrange
    provenance = _provenance()

    # Act — the persisted JSON IS the provenance (camelCase wire, like every CourseModel).
    restored = VideoProvenance.model_validate_json(provenance.model_dump_json(by_alias=True))

    # Assert
    assert restored == provenance
    assert restored.claim_ids == ["c1", "c3"]


def test_artifact_carries_provenance_and_round_trips() -> None:
    # Arrange
    artifact = _artifact()

    # Act
    restored = VideoArtifact.model_validate_json(artifact.model_dump_json(by_alias=True))

    # Assert — the artifact's defining payload is its grounding provenance.
    assert restored == artifact
    assert restored.provenance.claim_ids == ["c1", "c3"]
    assert restored.provenance.contract_hash == "abc123"


def test_a_lesson_can_carry_a_video_artifact_in_the_course_payload() -> None:
    # Arrange — a lesson with a finished video; the field defaults to None (populated by the build
    # in V4), so this proves the course payload CAN carry provenance end to end.
    segments = MerrillSegments(
        activate=Segment(prose="a"),
        demonstrate=Segment(prose="b"),
        apply=Segment(prose="c"),
        integrate=Segment(prose="d"),
    )
    lesson = Lesson(id="lesson-1", segments=segments, video=_artifact())
    course = Course(
        id="course-1",
        topic="Algorithms",
        modules=[Module(id="m1", title="Sorting", lessons=[lesson])],
    )

    # Act — round-trip the whole course payload.
    restored = Course.model_validate_json(course.model_dump_json(by_alias=True))

    # Assert — the provenance survived the full payload traversal.
    restored_lesson = restored.modules[0].lessons[0]
    assert restored_lesson.video is not None
    assert restored_lesson.video.provenance.claim_ids == ["c1", "c3"]


def test_a_lesson_without_a_video_defaults_to_none() -> None:
    # Arrange / Act — a lesson built before videos (or with the feature off) carries no video.
    segments = MerrillSegments(
        activate=Segment(), demonstrate=Segment(), apply=Segment(), integrate=Segment()
    )
    lesson = Lesson(id="lesson-1", segments=segments)

    # Assert — backward compatible: the field is optional and absent by default.
    assert lesson.video is None
