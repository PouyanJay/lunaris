import hashlib


def video_input_hash(course_id: str, entity_id: str) -> str:
    """A video job's input fingerprint (the staleness key).

    ``entity_id`` is the ``lesson_id`` for a lesson job and the kind value (e.g. ``"summary"``) for
    a course-level job (V5) — so each video kind fingerprints distinctly. Currently fingerprints the
    coordinates only; folding content + config in (so a revised input invalidates its cached video)
    is deferred to the staleness pass (plan §8.1). Shared by the build coordinator and the on-demand
    enqueue endpoint so the same input hashes identically on either path.
    """
    return hashlib.sha256(f"{course_id}/{entity_id}".encode()).hexdigest()
