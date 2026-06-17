import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind

from .lease_sweep_result import LeaseSweepResult
from .persistence_error import PersistenceError

# The terminal statuses a job settles into — READY/FAILED, plus CANCELLED (the owner stopped it).
# A terminal job is excluded from "active" (so a restart enqueues fresh, never the cancelled job),
# is never resurrected by a stage write, and is skipped by the lease sweep.
_TERMINAL = (VideoJobStatus.READY, VideoJobStatus.FAILED, VideoJobStatus.CANCELLED)


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

    async def update_status(self, *, job_id: str, status: VideoJobStatus) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            # Best-effort progress write: never resurrect a settled job (a stage racing the settle
            # must not un-settle it), and a vanished job is a silent no-op — unlike the settle
            # writes, a progress update must never fail the render.
            if job is None or job.status in _TERMINAL:
                return
            job.status = status
            job.updated_at = self._clock()

    async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
        await self._settle(job_id, VideoJobStatus.READY, error=None, contract_hash=contract_hash)

    async def fail(self, *, job_id: str, error: str) -> None:
        await self._settle(job_id, VideoJobStatus.FAILED, error=error)

    async def cancel(self, *, job_id: str, owner_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            # Owner-scoped + live-only: a missing, not-owned, or already-terminal job is a no-op.
            if job is None or job.user_id != owner_id or job.status in _TERMINAL:
                return False
            job.status = VideoJobStatus.CANCELLED
            # Release the lease so the sweep ignores it (it is terminal regardless).
            job.claimed_at = None
            job.claimed_by = None
            job.updated_at = self._clock()
            return True

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

    async def find_latest_ready(
        self, *, course_id: str, lesson_id: str | None, kind: VideoKind, owner_id: str
    ) -> VideoJob | None:
        async with self._lock:
            ready = [
                job
                for job in self._jobs.values()
                if job.user_id == owner_id
                and job.course_id == course_id
                and job.lesson_id == lesson_id
                and job.kind == kind
                and job.status == VideoJobStatus.READY
            ]
            if not ready:
                return None
            # Most recent first — same direction as the Supabase query's order(desc).limit(1).
            ready.sort(key=lambda job: (job.created_at or self._clock(), job.id), reverse=True)
            return ready[0].model_copy(deep=True)

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
            if job.status is VideoJobStatus.CANCELLED:
                # The owner stopped this job; a worker finishing the final render second must not
                # revive it. CANCELLED is sticky-terminal — complete/fail are a no-op.
                return
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
