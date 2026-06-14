from typing import Protocol

from lunaris_runtime.schema import VideoJob, VideoKind


class IVideoJobQueue(Protocol):
    """The explainer-video job queue — Postgres-backed in production, in-memory for tests/dev.

    The API enqueues (after its flag/tier checks); the worker drains: ``claim`` atomically takes
    the oldest ``QUEUED`` job (flipping it to ``PLANNING`` and stamping the lease — concurrent
    claimers can never get the same job), ``heartbeat`` extends the lease mid-render so a requeue
    sweep can tell a working worker from a dead one, and ``complete``/``fail`` settle the job
    terminally. ``get`` is the read the API's status endpoint serves; ``owner_id`` scopes it to
    the caller's own jobs (the app belt over the DB's RLS belt).

    Backend failures raise ``PersistenceError`` — job state must never be silently wrong; the
    worker treats it as "this job is in doubt" and moves on rather than guessing.
    """

    async def enqueue(self, job: VideoJob) -> None: ...

    async def claim(self, *, worker_id: str) -> VideoJob | None: ...

    async def heartbeat(self, *, job_id: str) -> None: ...

    async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
        """Settle the job READY. ``contract_hash`` (the planned scene-contracts fingerprint) is
        written back when the pipeline produced one — the durable cross-process regeneration cache
        key (V4-T1); ``None`` leaves the column untouched (e.g. a producer that built none)."""
        ...

    async def fail(self, *, job_id: str, error: str) -> None: ...

    async def get(self, *, job_id: str, owner_id: str | None = None) -> VideoJob | None: ...

    async def find_active(
        self, *, course_id: str, lesson_id: str | None, kind: VideoKind, owner_id: str
    ) -> VideoJob | None:
        """The owner's most recent NON-terminal (queued or in-flight) job for this
        (course, lesson, kind), or ``None`` if none is live. The enqueue endpoint dedups against it:
        a second request for a video already being made returns that job instead of a duplicate."""
        ...
