from typing import Protocol

from lunaris_runtime.schema import CoverJob, CoverJobStatus

from .lease_sweep_result import LeaseSweepResult


class ICoverJobQueue(Protocol):
    """The course cover-image job queue — Postgres-backed in production, in-memory for tests/dev.

    Mirrors ``IVideoJobQueue`` but for the per-course cover: there is exactly one cover per course,
    so ``find_active`` keys on (course, owner) with no kind/lesson dimension. The API enqueues
    (after its OpenAI-key/tier check); the worker drains: ``claim`` atomically takes the oldest
    ``QUEUED`` job (flipping it to ``ART_DIRECTING`` and stamping the lease — concurrent claimers
    can never get the same job), ``heartbeat`` extends the lease mid-render, and
    ``complete``/``fail`` settle it terminally. ``get`` is the read the API's status endpoint
    serves; ``owner_id`` scopes
    it to the caller's own jobs (the app belt over the DB's RLS belt).

    Backend failures raise ``PersistenceError`` — job state must never be silently wrong.
    """

    async def enqueue(self, job: CoverJob) -> None: ...

    async def claim(self, *, worker_id: str) -> CoverJob | None: ...

    async def heartbeat(self, *, job_id: str) -> None: ...

    async def update_status(self, *, job_id: str, status: CoverJobStatus) -> None:
        """Reflect an in-flight stage (art_directing / rendering / qa / uploading) on the job row so
        the status read shows real progress. Best-effort and idempotent: it never moves a TERMINAL
        job, and a vanished or already-settled job is a silent no-op (a progress update must never
        fail the render)."""
        ...

    async def complete(self, *, job_id: str) -> None:
        """Settle the job READY."""
        ...

    async def fail(self, *, job_id: str, error: str) -> None: ...

    async def cancel(self, *, job_id: str, owner_id: str) -> bool:
        """Stop the owner's job before it finishes — set it CANCELLED, but only when it exists, is
        owned, and is NON-terminal. Returns whether it actually transitioned; an already-terminal,
        missing, or not-owned job is an idempotent no-op returning ``False``. ``complete``/``fail``
        never overwrite a CANCELLED job, so the owner's stop wins even against a render finishing in
        the same instant."""
        ...

    async def get(self, *, job_id: str, owner_id: str | None = None) -> CoverJob | None: ...

    async def find_active(self, *, course_id: str, owner_id: str) -> CoverJob | None:
        """The owner's most recent NON-terminal (queued or in-flight) cover job for this course, or
        ``None``. The enqueue endpoint dedups against it: a second request for a cover already being
        made returns that job instead of a duplicate."""
        ...

    async def find_latest_ready(self, *, course_id: str, owner_id: str) -> CoverJob | None:
        """The owner's most recent READY cover job for this course, or ``None``. The reader's
        re-attach probe surfaces it when nothing is in flight, so a successful regenerate is still
        shown and re-resolves on every reload."""
        ...

    async def sweep_stale_leases(
        self, *, lease_seconds: int, max_attempts: int
    ) -> LeaseSweepResult:
        """Recover jobs a dead worker left in-flight past the lease: requeue those with attempts
        left, dead-letter (fail) those that have hit ``max_attempts``. Idempotent and atomic — a
        live render's lease stays fresh via ``heartbeat``, so only genuinely stuck jobs match."""
        ...

    async def list_for_course(self, *, course_id: str, owner_id: str) -> list[CoverJob]:
        """Every cover job (any status) for the owner's course — the artifact-path source for the
        course-deletion storage cascade."""
        ...

    async def delete_for_course(self, *, course_id: str, owner_id: str) -> int:
        """Delete all of the owner's cover job rows for a course; returns the row count removed.
        Storage objects are purged separately (storage.objects rejects SQL deletes)."""
        ...
