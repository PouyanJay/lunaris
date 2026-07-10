import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from lunaris_runtime.schema import CoverJob, CoverJobStatus

from .lease_sweep_result import LeaseSweepResult
from .persistence_error import PersistenceError

# The terminal statuses a cover job settles into — READY/FAILED, plus CANCELLED (the owner stopped
# it). A terminal job is excluded from "active", is never resurrected by a stage write, and is
# skipped by the lease sweep.
_TERMINAL = (CoverJobStatus.READY, CoverJobStatus.FAILED, CoverJobStatus.CANCELLED)


class InMemoryCoverJobQueue:
    """The in-memory cover-job queue double: same claim/lease semantics as the Supabase queue.

    Serves tests and the keyless/local path. A single ``asyncio.Lock`` plays the role FOR UPDATE
    SKIP LOCKED plays in the real queue. Jobs are returned as copies; only the queue mutates its
    rows. Writes against an unknown job raise ``PersistenceError``. ``clock`` is injectable so
    lease-timing tests are deterministic.
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._jobs: dict[str, CoverJob] = {}
        self._lock = asyncio.Lock()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def enqueue(self, job: CoverJob) -> None:
        async with self._lock:
            stored = job.model_copy(deep=True)
            stored.status = CoverJobStatus.QUEUED
            stored.created_at = stored.created_at or self._clock()
            stored.updated_at = stored.created_at
            self._jobs[job.id] = stored

    async def claim(self, *, worker_id: str) -> CoverJob | None:
        async with self._lock:
            queued = sorted(
                (job for job in self._jobs.values() if job.status == CoverJobStatus.QUEUED),
                key=lambda job: (job.created_at or self._clock(), job.id),
            )
            if not queued:
                return None
            job = self._jobs[queued[0].id]  # the live row, not a copy
            job.status = CoverJobStatus.ART_DIRECTING
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

    async def update_status(self, *, job_id: str, status: CoverJobStatus) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            # Best-effort progress write: never resurrect a settled job, and a vanished job is a
            # silent no-op — a progress update must never fail the render.
            if job is None or job.status in _TERMINAL:
                return
            job.status = status
            job.updated_at = self._clock()

    async def complete(self, *, job_id: str) -> None:
        await self._settle(job_id, CoverJobStatus.READY, error=None)

    async def fail(self, *, job_id: str, error: str) -> None:
        await self._settle(job_id, CoverJobStatus.FAILED, error=error)

    async def cancel(self, *, job_id: str, owner_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.user_id != owner_id or job.status in _TERMINAL:
                return False
            job.status = CoverJobStatus.CANCELLED
            job.claimed_at = None  # release the lease so the sweep ignores it (terminal regardless)
            job.claimed_by = None
            job.updated_at = self._clock()
            return True

    async def get(self, *, job_id: str, owner_id: str | None = None) -> CoverJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or (owner_id is not None and job.user_id != owner_id):
                return None
            return job.model_copy(deep=True)

    async def find_active(self, *, course_id: str, owner_id: str) -> CoverJob | None:
        async with self._lock:
            active = [
                job
                for job in self._jobs.values()
                if job.user_id == owner_id
                and job.course_id == course_id
                and job.status not in _TERMINAL
            ]
            if not active:
                return None
            active.sort(key=lambda job: (job.created_at or self._clock(), job.id), reverse=True)
            return active[0].model_copy(deep=True)

    async def find_latest_ready(self, *, course_id: str, owner_id: str) -> CoverJob | None:
        async with self._lock:
            ready = [
                job
                for job in self._jobs.values()
                if job.user_id == owner_id
                and job.course_id == course_id
                and job.status == CoverJobStatus.READY
            ]
            if not ready:
                return None
            ready.sort(key=lambda job: (job.created_at or self._clock(), job.id), reverse=True)
            return ready[0].model_copy(deep=True)

    async def sweep_stale_leases(
        self, *, lease_seconds: int, max_attempts: int
    ) -> LeaseSweepResult:
        async with self._lock:
            cutoff = self._clock() - timedelta(seconds=lease_seconds)
            requeued = dead_lettered = 0
            for job in self._jobs.values():
                if job.status in _TERMINAL or job.status == CoverJobStatus.QUEUED:
                    continue
                if job.claimed_at is None or job.claimed_at >= cutoff:
                    continue
                if job.attempts >= max_attempts:
                    job.status = CoverJobStatus.FAILED
                    job.error = "cover generation failed (lease expired after max attempts)"
                    dead_lettered += 1
                else:
                    job.status = CoverJobStatus.QUEUED
                    requeued += 1
                job.claimed_at = None
                job.claimed_by = None
                job.updated_at = self._clock()
            return LeaseSweepResult(requeued=requeued, dead_lettered=dead_lettered)

    async def list_for_course(self, *, course_id: str, owner_id: str) -> list[CoverJob]:
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

    async def _settle(self, job_id: str, status: CoverJobStatus, *, error: str | None) -> None:
        async with self._lock:
            job = self._require(job_id, operation=f"settle {status.value}")
            if job.status is CoverJobStatus.CANCELLED:
                # The owner stopped this job; a worker finishing the render second must not revive
                # it. CANCELLED is sticky-terminal — complete/fail are a no-op.
                return
            job.status = status
            job.error = error
            job.updated_at = self._clock()

    def _require(self, job_id: str, *, operation: str) -> CoverJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise PersistenceError(f"{operation}: cover job {job_id!r} not found")
        return job
