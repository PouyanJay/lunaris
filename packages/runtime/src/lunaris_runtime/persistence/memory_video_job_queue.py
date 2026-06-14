import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind

from .lease_sweep_result import LeaseSweepResult
from .persistence_error import PersistenceError

# The non-terminal statuses a job passes through before READY/FAILED — "active" for dedup.
_TERMINAL = (VideoJobStatus.READY, VideoJobStatus.FAILED)


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

    async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
        await self._settle(job_id, VideoJobStatus.READY, error=None, contract_hash=contract_hash)

    async def fail(self, *, job_id: str, error: str) -> None:
        await self._settle(job_id, VideoJobStatus.FAILED, error=error)

    async def get(self, *, job_id: str, owner_id: str | None = None) -> VideoJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or (owner_id is not None and job.user_id != owner_id):
                return None
            return job.model_copy(deep=True)

    async def find_active(
        self, *, course_id: str, lesson_id: str | None, kind: VideoKind, owner_id: str
    ) -> VideoJob | None:
        async with self._lock:
            active = [
                job
                for job in self._jobs.values()
                if job.user_id == owner_id
                and job.course_id == course_id
                and job.lesson_id == lesson_id
                and job.kind == kind
                and job.status not in _TERMINAL
            ]
            if not active:
                return None
            # Most recent first — same direction as the Supabase query's order(desc).limit(1).
            active.sort(key=lambda job: (job.created_at or self._clock(), job.id), reverse=True)
            return active[0].model_copy(deep=True)

    async def sweep_stale_leases(
        self, *, lease_seconds: int, max_attempts: int
    ) -> LeaseSweepResult:
        async with self._lock:
            cutoff = self._clock() - timedelta(seconds=lease_seconds)
            requeued = dead_lettered = 0
            for job in self._jobs.values():
                # Only stale IN-FLIGHT jobs (claimed, not terminal, not already back in the queue)
                # with a lease older than the cutoff — a live render's heartbeat keeps it fresh.
                if job.status in _TERMINAL or job.status == VideoJobStatus.QUEUED:
                    continue
                if job.claimed_at is None or job.claimed_at >= cutoff:
                    continue
                if job.attempts >= max_attempts:
                    job.status = VideoJobStatus.FAILED
                    job.error = "video generation failed (lease expired after max attempts)"
                    dead_lettered += 1
                else:
                    job.status = VideoJobStatus.QUEUED
                    requeued += 1
                job.claimed_at = None
                job.claimed_by = None
                job.updated_at = self._clock()
            return LeaseSweepResult(requeued=requeued, dead_lettered=dead_lettered)

    async def list_for_course(self, *, course_id: str, owner_id: str) -> list[VideoJob]:
        async with self._lock:
            return [
                job.model_copy(deep=True)
                for job in self._jobs.values()
                if job.user_id == owner_id and job.course_id == course_id
            ]

    async def delete_for_course(self, *, course_id: str, owner_id: str) -> int:
        async with self._lock:
            doomed = [
                job_id
                for job_id, job in self._jobs.items()
                if job.user_id == owner_id and job.course_id == course_id
            ]
            for job_id in doomed:
                del self._jobs[job_id]
            return len(doomed)

    async def _settle(
        self,
        job_id: str,
        status: VideoJobStatus,
        *,
        error: str | None,
        contract_hash: str | None = None,
    ) -> None:
        async with self._lock:
            job = self._require(job_id, operation=f"settle {status.value}")
            job.status = status
            job.error = error
            if contract_hash is not None:
                job.contract_hash = contract_hash
            job.updated_at = self._clock()

    def _require(self, job_id: str, *, operation: str) -> VideoJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise PersistenceError(f"{operation}: video job {job_id!r} not found")
        return job
