import hashlib
import uuid

from lunaris_runtime.persistence import ICoverJobQueue
from lunaris_runtime.schema import Course, CoverJob, CoverStylePreset


def cover_input_hash(course: Course, style_preset: CoverStylePreset) -> str:
    """Fingerprint a cover's generation inputs — the course topic + the chosen art-direction
    preset — so a later staleness check can flag a cover outdated when the topic (or preset)
    changes. The course id is folded in too so the hash is unique per course, even across topics."""
    digest = hashlib.sha256()
    digest.update(course.id.encode())
    digest.update(b"\x00")
    digest.update(course.topic.encode())
    digest.update(b"\x00")
    digest.update(style_preset.value.encode())
    return digest.hexdigest()


async def enqueue_cover_job(
    queue: ICoverJobQueue,
    *,
    course: Course,
    owner_id: str,
    style_preset: CoverStylePreset,
) -> tuple[CoverJob, bool]:
    """Enqueue one cover job for ``course``, deduped against an in-flight one (there is exactly one
    cover per course). Returns ``(job, created)``: the existing in-flight job when one is already
    active (``created=False`` — never stack a second), else the freshly enqueued QUEUED job. The one
    place the enqueue is built, shared by the API enqueue/regenerate routes and the build-completion
    auto-enqueue, so the dedup + input-hash rules can never drift between them."""
    existing = await queue.find_active(course_id=course.id, owner_id=owner_id)
    if existing is not None:
        return existing, False
    job = CoverJob(
        id=uuid.uuid4().hex,
        user_id=owner_id,
        course_id=course.id,
        style_preset=style_preset,
        input_hash=cover_input_hash(course, style_preset),
    )
    await queue.enqueue(job)
    return job, True
