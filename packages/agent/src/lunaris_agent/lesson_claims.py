from collections.abc import Iterator

from lunaris_runtime.schema import Claim, Lesson, Segment


def lesson_segments(lesson: Lesson) -> tuple[Segment, ...]:
    """The four Merrill segments of a lesson, in teaching order."""
    s = lesson.segments
    return (s.activate, s.demonstrate, s.apply, s.integrate)


def iter_claims(lessons: list[Lesson]) -> Iterator[Claim]:
    """Every claim across a set of lessons — the verifier's work list."""
    for lesson in lessons:
        for segment in lesson_segments(lesson):
            yield from segment.claims
