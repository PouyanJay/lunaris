from typing import Protocol


class IVideoStorage(Protocol):
    """Binary artifact storage for explainer videos — the ``course-videos`` bucket.

    The worker ``upload``s rendered artifacts (service path; the bucket is private and only
    service_role writes objects); the API issues short-lived ``signed_url``s for playback — the
    reader's player never touches storage credentials — and ``download``s small JSON artifacts
    (provenance) to thread onto the wire. Paths follow the ``{user_id}/{course_id}/{job_id}/…``
    convention (see ``VideoArtifactPaths``).

    Backend failures raise ``PersistenceError`` — an upload that didn't land must fail the job,
    never present a half-written artifact as done.
    """

    async def upload(self, *, path: str, data: bytes, content_type: str) -> None: ...

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str: ...

    async def download(self, *, path: str) -> bytes: ...

    async def delete(self, *, paths: list[str]) -> None:
        """Remove the given object paths (the course-deletion storage cascade, V7-T4). Idempotent —
        a path that doesn't exist is a no-op, never an error — so deleting a job's full artifact set
        is safe even when a FAILED job only ever wrote some of them. Uses the Storage API (not SQL;
        storage.objects rejects direct deletes)."""
        ...
