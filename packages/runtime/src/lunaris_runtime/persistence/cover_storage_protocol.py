from typing import Protocol


class ICoverStorage(Protocol):
    """Binary artifact storage for course cover images — the ``course-covers`` bucket.

    The worker ``upload``s the rendered image (service path; the bucket is private and only
    service_role writes objects); the API issues short-lived ``signed_url``s for display — the
    reader never touches storage credentials — and ``download``s the small provenance JSON to thread
    onto the wire. Paths follow the ``{user_id}/{course_id}/{job_id}/…`` convention (see
    ``CoverArtifactPaths``).

    Backend failures raise ``PersistenceError`` — an upload that didn't land must fail the job,
    never present a half-written cover as done.
    """

    async def upload(self, *, path: str, data: bytes, content_type: str) -> None: ...

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str: ...

    async def download(self, *, path: str) -> bytes: ...

    async def delete(self, *, paths: list[str]) -> None:
        """Remove the given object paths (the course-deletion storage cascade). Idempotent — a path
        that doesn't exist is a no-op. Uses the Storage API (SQL deletes on storage.objects
        fail)."""
        ...
