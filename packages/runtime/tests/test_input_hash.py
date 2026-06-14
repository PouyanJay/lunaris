"""V6-T3: the staleness key — the video input hash folds the source content + the chosen length.

A re-authored lesson (or a changed length) fingerprints differently, so the reader can flag a built
video as outdated. The lesson content fingerprint excludes the stitched ``video`` (derived, so
including it would be circular)."""

from lunaris_runtime.schema import Lesson, MerrillSegments, Segment, VideoArtifact, VideoKind
from lunaris_runtime.video_build import (
    lesson_content_fingerprint,
    lesson_video_input_hash,
    video_input_hash,
)


def _lesson(lesson_id: str = "m0-l0", *, expects: list[str] | None = None) -> Lesson:
    return Lesson(
        id=lesson_id,
        segments=MerrillSegments(
            activate=Segment(), demonstrate=Segment(), apply=Segment(), integrate=Segment()
        ),
        expects=expects or ["bring algebra"],
    )


def test_video_input_hash_distinguishes_coordinates_content_and_length() -> None:
    base = video_input_hash("c1", "m0-l0", content_hash="abc", target_seconds=75)
    # Stable for the same inputs.
    assert base == video_input_hash("c1", "m0-l0", content_hash="abc", target_seconds=75)
    # Each axis changes the hash.
    assert base != video_input_hash("c2", "m0-l0", content_hash="abc", target_seconds=75)
    assert base != video_input_hash("c1", "m0-l1", content_hash="abc", target_seconds=75)
    assert base != video_input_hash("c1", "m0-l0", content_hash="xyz", target_seconds=75)
    assert base != video_input_hash("c1", "m0-l0", content_hash="abc", target_seconds=90)


def test_video_input_hash_is_not_confused_by_delimiter_characters() -> None:
    # A field with a separator must not alias a different split (the JSON preimage guards this).
    assert video_input_hash("a/b", "c", content_hash="", target_seconds=75) != video_input_hash(
        "a", "b/c", content_hash="", target_seconds=75
    )


def test_lesson_content_fingerprint_changes_with_the_content() -> None:
    a = lesson_content_fingerprint(_lesson(expects=["bring algebra"]))
    b = lesson_content_fingerprint(_lesson(expects=["bring calculus"]))
    assert a != b
    # Stable for identical content.
    assert a == lesson_content_fingerprint(_lesson(expects=["bring algebra"]))


def test_lesson_content_fingerprint_ignores_the_stitched_video() -> None:
    # The video is derived from the content, so adding it must NOT change the fingerprint (else
    # stitching the video would immediately mark it outdated — a circular dependency).
    without = _lesson()
    with_video = without.model_copy(
        update={"video": VideoArtifact(kind=VideoKind.LESSON, status="ready", job_id="job-1")}
    )
    assert lesson_content_fingerprint(without) == lesson_content_fingerprint(with_video)


def test_lesson_video_input_hash_combines_content_and_length() -> None:
    lesson = _lesson()
    combined = lesson_video_input_hash("c1", lesson, target_seconds=75)
    assert combined == video_input_hash(
        "c1", lesson.id, content_hash=lesson_content_fingerprint(lesson), target_seconds=75
    )
    # A revised lesson or a different length yields a different hash.
    assert combined != lesson_video_input_hash("c1", lesson, target_seconds=90)
    assert combined != lesson_video_input_hash("c1", _lesson(expects=["new"]), target_seconds=75)
