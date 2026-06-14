import hashlib


def video_input_hash(course_id: str, lesson_id: str) -> str:
    """The lesson-video job's input fingerprint (the staleness key).

    Currently fingerprints the lesson coordinates only; folding the lesson content + config in (so a
    revised lesson invalidates its cached video) is deferred to the staleness pass (plan §8.1).
    Shared by the build coordinator and the on-demand enqueue endpoint so the same lesson hashes
    identically on either path.
    """
    return hashlib.sha256(f"{course_id}/{lesson_id}".encode()).hexdigest()
