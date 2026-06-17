import asyncio
import os
from datetime import UTC, datetime

from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind

from .guard import guard
from .lease_sweep_result import LeaseSweepResult
from .persistence_error import PersistenceError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "video_jobs"
_CLAIM_RPC = "claim_video_job"
_SWEEP_RPC = "requeue_stale_video_jobs"
# The terminal statuses a job settles into — READY/FAILED, plus CANCELLED (the owner stopped it). A
# terminal job is excluded from the "active" dedup read, is never resurrected by a stage write, and
# is skipped by the lease sweep.
_TERMINAL_STATUSES = (
    VideoJobStatus.READY.value,
    VideoJobStatus.FAILED.value,
    VideoJobStatus.CANCELLED.value,
)


class SupabaseVideoJobQueue:
    """The production video-job queue: Supabase Postgres, lazy service-role client.

    Same access posture as the other Supabase stores (service_role bypasses RLS; the table's
    user-facing surface is owner-scoped SELECT only). The one special move is ``claim``: PostgREST
    cannot express FOR UPDATE SKIP LOCKED, so the atomic claim lives in the ``claim_video_job``
    DB function (V0-T1 migration) and this client just calls it — the row lock, not Python,
    guarantees two workers never get the same job. ``updated_at`` is app-maintained on every
    write (repo convention — no DB trigger).
    """

    def __init__(
        self,
        *,
        url_env: str = _URL_ENV,
        service_key_env: str = _SERVICE_KEY_ENV,
        client: object | None = None,
    ) -> None:
        self._url_env = url_env
        self._service_key_env = service_key_env
        # An injected client (tests) skips lazy construction; production builds from env on
        # first use so the composition root can construct this unconditionally.
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot reach video_jobs"
                )
            self._client = create_client(url, key)
        return self._client

    @guard("video_jobs enqueue")
    async def enqueue(self, job: VideoJob) -> None:
        client = self._ensure_client()
        # The row carries the queue contract; status is forced to queued and timestamps stay
        # DB-owned, whatever the caller's VideoJob instance happens to hold.
        row: dict[str, object] = {
            "id": job.id,
            "user_id": job.user_id,
            "course_id": job.course_id,
            "lesson_id": job.lesson_id,
            "kind": job.kind.value,
            "status": VideoJobStatus.QUEUED.value,
            "input_hash": job.input_hash,
            "config": job.config,
        }
        await asyncio.to_thread(lambda: client.table(_TABLE).insert(row).execute())  # type: ignore[attr-defined]

    @guard("video_jobs claim")
    async def claim(self, *, worker_id: str) -> VideoJob | None:
        client = self._ensure_client()

        def _run() -> object:
            return client.rpc(_CLAIM_RPC, {"p_worker": worker_id}).execute()  # type: ignore[attr-defined]

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return VideoJob.model_validate(rows[0]) if rows else None

    @guard("video_jobs heartbeat")
    async def heartbeat(self, *, job_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._patch(job_id, {"claimed_at": now, "updated_at": now})

    @guard("video_jobs update_status")
    async def update_status(self, *, job_id: str, status: VideoJobStatus) -> None:
        client = self._ensure_client()
        patch = {"status": status.value, "updated_at": datetime.now(UTC).isoformat()}

        # Filter on non-terminal so a stage write that races the settle never resurrects a READY/
        # FAILED job. A 0-row update (job settled or gone) is a deliberate no-op here, NOT the
        # PersistenceError that `_patch` raises — a best-effort progress write must never fail the
        # render. (`@guard` still surfaces a genuine backend error as PersistenceError.)
        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .update(patch)
                .eq("id", job_id)
                .not_.in_("status", list(_TERMINAL_STATUSES))
                .execute()
            )

        await asyncio.to_thread(_run)

    @guard("video_jobs complete")
    async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
        patch: dict[str, object] = {
            "status": VideoJobStatus.READY.value,
            "error": None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        # Write the planned contract fingerprint back (the regeneration cache key, V4-T1) only when
        # the pipeline produced one; never clobber an existing value with null.
        if contract_hash is not None:
            patch["contract_hash"] = contract_hash
        await self._settle(job_id, patch)

    @guard("video_jobs fail")
    async def fail(self, *, job_id: str, error: str) -> None:
        await self._settle(
            job_id,
            {
                "status": VideoJobStatus.FAILED.value,
                "error": error,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    @guard("video_jobs cancel")
    async def cancel(self, *, job_id: str, owner_id: str) -> bool:
        client = self._ensure_client()
        patch = {
            "status": VideoJobStatus.CANCELLED.value,
            "claimed_at": None,  # release the lease so the sweep ignores it (it's terminal anyway)
            "claimed_by": None,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        # Owner-scoped + live-only (NOT IN terminal); count="exact" reports whether a live, owned
        # row transitioned — a missing / not-owned / already-terminal job is a no-op (False).
        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .update(patch, count="exact")
                .eq("id", job_id)
                .eq("user_id", owner_id)
                .not_.in_("status", list(_TERMINAL_STATUSES))
                .execute()
            )

        response = await asyncio.to_thread(_run)
        return bool(getattr(response, "count", None) or 0)

    @guard("video_jobs get")
    async def get(self, *, job_id: str, owner_id: str | None = None) -> VideoJob | None:
        client = self._ensure_client()

        def _run() -> object:
            query = client.table(_TABLE).select("*").eq("id", job_id)  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # only the owner reads their job
            return query.limit(1).execute()

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return VideoJob.model_validate(rows[0]) if rows else None

    @guard("video_jobs find_active")
    async def find_active(
        self, *, course_id: str, lesson_id: str | None, kind: VideoKind, owner_id: str
    ) -> VideoJob | None:
        client = self._ensure_client()

        def _run() -> object:
            query = (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("*")
                .eq("user_id", owner_id)  # owner-scoped (the app belt over the DB's RLS belt)
                .eq("course_id", course_id)
                .eq("kind", kind.value)
                .not_.in_("status", list(_TERMINAL_STATUSES))  # queued or still in flight
            )
            # PostgREST: a null lesson_id (course-level kinds) needs `is`, not `eq`.
            query = (
                query.is_("lesson_id", "null")
                if lesson_id is None
                else query.eq("lesson_id", lesson_id)
            )
            return query.order("created_at", desc=True).limit(1).execute()

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return VideoJob.model_validate(rows[0]) if rows else None

    @guard("video_jobs find_latest_ready")
    async def find_latest_ready(
        self, *, course_id: str, lesson_id: str | None, kind: VideoKind, owner_id: str
    ) -> VideoJob | None:
        client = self._ensure_client()

        def _run() -> object:
            query = (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("*")
                .eq("user_id", owner_id)  # owner-scoped (the app belt over the DB's RLS belt)
                .eq("course_id", course_id)
                .eq("kind", kind.value)
                .eq("status", VideoJobStatus.READY.value)  # only a finished, playable render
            )
            # PostgREST: a null lesson_id (course-level kinds) needs `is`, not `eq`.
            query = (
                query.is_("lesson_id", "null")
                if lesson_id is None
                else query.eq("lesson_id", lesson_id)
            )
            return query.order("created_at", desc=True).limit(1).execute()

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return VideoJob.model_validate(rows[0]) if rows else None

    @guard("video_jobs sweep")
    async def sweep_stale_leases(
        self, *, lease_seconds: int, max_attempts: int
    ) -> LeaseSweepResult:
        client = self._ensure_client()

        def _run() -> object:
            return client.rpc(  # type: ignore[attr-defined]
                _SWEEP_RPC,
                {"p_lease_seconds": lease_seconds, "p_max_attempts": max_attempts},
            ).execute()

        response = await asyncio.to_thread(_run)
        rows = response.data or [{}]
        row = rows[0]
        return LeaseSweepResult(
            requeued=int(row.get("requeued") or 0),
            dead_lettered=int(row.get("dead_lettered") or 0),
        )

    @guard("video_jobs list_for_course")
    async def list_for_course(self, *, course_id: str, owner_id: str) -> list[VideoJob]:
        client = self._ensure_client()

        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("*")
                .eq("user_id", owner_id)  # owner-scoped (the app belt over the DB's RLS belt)
                .eq("course_id", course_id)
                .execute()
            )

        response = await asyncio.to_thread(_run)
        return [VideoJob.model_validate(row) for row in (response.data or [])]

    @guard("video_jobs delete_for_course")
    async def delete_for_course(self, *, course_id: str, owner_id: str) -> int:
        client = self._ensure_client()

        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .delete(count="exact")
                .eq("user_id", owner_id)
                .eq("course_id", course_id)
                .execute()
            )

        response = await asyncio.to_thread(_run)
        return int(getattr(response, "count", None) or 0)

    async def _patch(self, job_id: str, patch: dict[str, object]) -> None:
        client = self._ensure_client()

        # count="exact" so "the job vanished" surfaces as PersistenceError instead of a silent
        # zero-row no-op — the protocol contract is that job state is never silently wrong
        # (mirrors the in-memory double's raise; the requeue sweep may legitimately reap rows).
        def _run() -> object:
            return client.table(_TABLE).update(patch, count="exact").eq("id", job_id).execute()  # type: ignore[attr-defined]

        response = await asyncio.to_thread(_run)
        if not (getattr(response, "count", None) or 0):
            raise PersistenceError(f"video job {job_id!r} not found")

    async def _settle(self, job_id: str, patch: dict[str, object]) -> None:
        """A terminal settle (complete/fail) that never overwrites a CANCELLED job — the owner's
        stop wins even if the render finished in the same instant. Zero rows ⇒ the job is gone OR
        already cancelled: a cancelled row is a benign no-op (the stop is authoritative); a missing
        row is the PersistenceError the protocol demands (job state never silently wrong)."""
        client = self._ensure_client()

        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .update(patch, count="exact")
                .eq("id", job_id)
                .neq("status", VideoJobStatus.CANCELLED.value)
                .execute()
            )

        response = await asyncio.to_thread(_run)
        if getattr(response, "count", None) or 0:
            return
        # Zero rows: tell a benign cancelled job (no-op) apart from a genuinely missing one (error).
        # A transient blip on the disambiguation read must not turn a settle into a spurious failure
        # (which would loop the job through the lease sweep) — treat an unreadable row as benign,
        # since the only reason the settle hit zero rows is the cancelled guard or a vanished row.
        try:
            existing = await self.get(job_id=job_id)
        except PersistenceError:
            return
        if existing is not None and existing.status is VideoJobStatus.CANCELLED:
            return
        raise PersistenceError(f"video job {job_id!r} not found")
