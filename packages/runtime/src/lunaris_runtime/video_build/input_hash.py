import hashlib
import json

from ..schema import Lesson


def video_input_hash(
    course_id: str, entity_id: str, *, content_hash: str = "", target_seconds: int = 0
) -> str:
    """A video job's input fingerprint — the staleness key (plan §8.1).

    ``entity_id`` is the ``lesson_id`` for a lesson job and the kind value (e.g. ``"summary"``) for
    a course-level job (V5). V6-T3 folds the source **content** (``content_hash`` — a lesson's
    content) and the **config** (``target_seconds``) into the hash, so a revised lesson or a changed
    length fingerprints differently and the reader can flag the built video as outdated.
    Course-level jobs pass no ``content_hash`` (lesson-revision staleness doesn't apply to a
    trailer/intro), only their length. Shared by the build coordinator, the on-demand endpoint, and
    the staleness check so the same input hashes identically everywhere.
    """
    # JSON-list preimage (not a slash-joined string) so a field that ever contained a ``/`` can't
    # alias a different field split — the delimiter is unambiguous regardless of the input shape.
    preimage = json.dumps(
        [course_id, entity_id, content_hash, target_seconds], separators=(",", ":")
    )
    return hashlib.sha256(preimage.encode()).hexdigest()


def lesson_content_fingerprint(lesson: Lesson) -> str:
    """A stable hash of a lesson's authored content — everything but the stitched ``video`` (which
    is derived from it, so including it would be circular). A re-authored lesson (its segments / arc
    change) fingerprints differently; this is the content half of the staleness key (V6-T3)."""
    # model_dump with by_alias=False (the default) hashes Python field names, not the camelCase
    # aliases — sort_keys canonicalises ordering. (Adding serialize_by_alias to CourseModel would
    # silently change every stored hash, so keep this explicit.)
    payload = lesson.model_dump(mode="json", exclude={"video"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def lesson_video_input_hash(course_id: str, lesson: Lesson, *, target_seconds: int) -> str:
    """The input hash for a lesson's video: the lesson coordinates + its content fingerprint + the
    target length. The one place the three are combined, so the build path, the on-demand enqueue,
    and the staleness recomputation all agree on what "the same input" means."""
    return video_input_hash(
        course_id,
        lesson.id,
        content_hash=lesson_content_fingerprint(lesson),
        target_seconds=target_seconds,
    )
