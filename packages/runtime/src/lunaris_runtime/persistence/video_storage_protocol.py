from typing import Protocol


class IVideoStorage(Protocol):
    """Binary artifact storage for explainer videos — the ``course-videos`` bucket.

    The worker ``upload``s rendered artifacts (service path; the bucket is private and only
    service_role writes objects); the API issues short-lived ``signed_url``s for playback — the
    reader's player never touches storage credentials. Paths follow the
    ``{user_id}/{course_id}/{job_id}/…`` convention (see ``VideoArtifactPaths``).

    Backend failures raise ``PersistenceError`` — an upload that didn't land must fail the job,
    never present a half-written artifact as done.
    """

    async def upload(self, *, path: str, data: bytes, content_type: str) -> None: ...

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str: ...
