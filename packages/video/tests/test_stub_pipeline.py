"""Stub-pipeline tests: the packaged placeholder artifacts are real, playable media files."""

from lunaris_runtime.schema import VideoJob, VideoKind
from lunaris_video import StubVideoPipeline


def _job() -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-1",
    )


async def test_produce_returns_a_real_mp4_and_jpeg() -> None:
    # Arrange
    pipeline = StubVideoPipeline()

    # Act
    rendered = await pipeline.produce(_job())

    # Assert — honest media, not placeholder bytes: an ISO Media ftyp box and a JPEG SOI marker.
    # The reader's player must actually play the walking skeleton's artifact.
    assert rendered.mp4[4:8] == b"ftyp"
    assert rendered.poster[:3] == b"\xff\xd8\xff"
    assert len(rendered.mp4) > 1000
    assert len(rendered.poster) > 500
