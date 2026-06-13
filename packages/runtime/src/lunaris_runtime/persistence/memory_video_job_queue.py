import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from lunaris_runtime.schema import VideoJob, VideoJobStatus

from .persistence_error import PersistenceError


class InMemoryVideoJobQueue:
    """The in-memory queue double: same claim/lease semantics as the Supabase queue, no Postgres.

    Serves tests and the keyless/local path. A single ``asyncio.Lock`` plays the role FOR UPDATE
    SKIP LOCKED plays in the real queue — claims are mutually exclusive, so concurrent claimers
    can never get the same job. Jobs are returned as copies; only the queue mutates its rows.
    Writes against an unknown job raise ``PersistenceError`` (protocol contract: job state must
    never be silently wrong), mirroring the Supabase queue's zero-rows check. ``clock`` is
    injectable so lease-timing tests are deterministic.
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._jobs: dict[str, VideoJob] = {}
        self._lock = asyncio.Lock()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def enqueue(self, job: VideoJob) -> None:
        async with self._lock:
            stored = job.model_copy(deep=True)
            stored.status = VideoJobStatus.QUEUED
            stored.created_at = stored.created_at or self._clock()
            stored.updated_at = stored.created_at
            self._jobs[job.id] = stored

    async def claim(self, *, worker_id: str) -> VideoJob | None:
        async with self._lock:
            queued = sorted(
                (job for job in self._jobs.values() if job.status == VideoJobStatus.QUEUED),
                key=lambda job: (job.created_at or self._clock(), job.id),
            )
            if not queued:
                return None
            job = self._jobs[queued[0].id]  # unambiguously the live row, not a copy
            job.status = VideoJobStatus.PLANNING
            job.claimed_at = self._clock()
            job.claimed_by = worker_id
            job.attempts += 1
            job.updated_at = job.claimed_at
            return job.model_copy(deep=True)

    async def heartbeat(self, *, job_id: str) -> None:
        async with self._lock:
            job = self._require(job_id, operation="heartbeat")
            job.claimed_at = self._clock()
            job.updated_at = job.claimed_at

    async def complete(self, *, job_id: str) -> None:
        await self._settle(job_id, VideoJobStatus.READY, error=None)

    async def fail(self, *, job_id: str, error: str) -> None:
        await self._settle(job_id, VideoJobStatus.FAILED, error=error)

    async def get(self, *, job_id: str, owner_id: str | None = None) -> VideoJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or (owner_id is not None and job.user_id != owner_id):
                return None
            return job.model_copy(deep=True)

    async def _settle(self, job_id: str, status: VideoJobStatus, *, error: str | None) -> None:
        async with self._lock:
            job = self._require(job_id, operation=f"settle {status.value}")
            job.status = status
            job.error = error
            job.updated_at = self._clock()

    def _require(self, job_id: str, *, operation: str) -> VideoJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise PersistenceError(f"{operation}: video job {job_id!r} not found")
        return job
