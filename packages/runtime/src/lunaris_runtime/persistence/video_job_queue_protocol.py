from typing import Protocol

from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind

from .lease_sweep_result import LeaseSweepResult


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

    async def update_status(self, *, job_id: str, status: VideoJobStatus) -> None:
        """Reflect an in-flight stage (e.g. voicing / rendering / assembling) on the job row so the
        status read shows real progress (the reader's progress bar). Which stages the pipeline
        actually reports is the producer's business. Best-effort and idempotent: it never moves a
        TERMINAL job — a late stage write that races a settle must not un-settle it — and a vanished
        or already-settled job is a silent no-op (unlike the settle writes, a progress update must
        never fail the render)."""
        ...

    async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
        """Settle the job READY. ``contract_hash`` (the planned scene-contracts fingerprint) is
        written back when the pipeline produced one — the durable cross-process regeneration cache
        key (V4-T1); ``None`` leaves the column untouched (e.g. a producer that built none)."""
        ...

    async def fail(self, *, job_id: str, error: str) -> None: ...

    async def cancel(self, *, job_id: str, owner_id: str) -> bool:
        """Stop the owner's job before it finishes — set it CANCELLED, but only when it exists, is
        owned, and is NON-terminal (queued or still in flight). Returns whether it actually
        transitioned: an already-terminal, missing, or not-owned job is an idempotent no-op
        returning ``False``. A cancelled QUEUED job is never claimed (``claim`` takes only queued
        rows), and a cancelled in-flight job is aborted by the worker's cancel-watcher — so no
        compute is spent on a stopped video. ``complete``/``fail`` never overwrite a CANCELLED job,
        so the owner's stop wins even against a render finishing in the same instant."""
        ...

    async def get(self, *, job_id: str, owner_id: str | None = None) -> VideoJob | None: ...

    async def find_active(
        self, *, course_id: str, lesson_id: str | None, kind: VideoKind, owner_id: str
    ) -> VideoJob | None:
        """The owner's most recent NON-terminal (queued or in-flight) job for this
        (course, lesson, kind), or ``None`` if none is live. The enqueue endpoint dedups against it:
        a second request for a video already being made returns that job instead of a duplicate."""
        ...

    async def find_latest_ready(
        self, *, course_id: str, lesson_id: str | None, kind: VideoKind, owner_id: str
    ) -> VideoJob | None:
        """The owner's most recent READY job for this (course, lesson, kind), or ``None``. The
        reader's re-attach probe surfaces it when nothing is in flight, so a successful regenerate
        that the persisted (build) artifact does not point to is still shown — and re-resolves on
        every reload — instead of the slot reverting to a stale failed/old built artifact."""
        ...

    async def sweep_stale_leases(
        self, *, lease_seconds: int, max_attempts: int
    ) -> LeaseSweepResult:
        """Recover jobs a dead worker left in-flight past the lease (V7-T4): requeue those with
        attempts left, dead-letter (fail) those that have hit ``max_attempts``. Idempotent and
        atomic — a live render's lease stays fresh via ``heartbeat``, so only genuinely stuck jobs
        match. Returns how many were requeued vs dead-lettered."""
        ...

    async def list_for_course(self, *, course_id: str, owner_id: str) -> list[VideoJob]:
        """Every job (any status) for the owner's course — the artifact-path source for the
        course-deletion storage cascade (V7-T4)."""
        ...

    async def delete_for_course(self, *, course_id: str, owner_id: str) -> int:
        """Delete all of the owner's job rows for a course (the queue side of course deletion);
        returns the row count removed. Storage objects are purged separately (storage.objects
        rejects SQL deletes — see ``IVideoStorage.delete``)."""
        ...
