import asyncio
import os
from datetime import UTC, datetime

from lunaris_runtime.schema import CoverJob, CoverJobStatus

from .guard import guard
from .lease_sweep_result import LeaseSweepResult
from .persistence_error import PersistenceError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "cover_jobs"
_CLAIM_RPC = "claim_cover_job"
_SWEEP_RPC = "requeue_stale_cover_jobs"
_TERMINAL_STATUSES = (
    CoverJobStatus.READY.value,
    CoverJobStatus.FAILED.value,
    CoverJobStatus.CANCELLED.value,
)


class SupabaseCoverJobQueue:
    """The production cover-job queue: Supabase Postgres, lazy service-role client.

    Mirrors ``SupabaseVideoJobQueue`` (service_role bypasses RLS; the table's user-facing surface is
    owner-scoped SELECT only). The atomic claim lives in the ``claim_cover_job`` DB function; this
    client just calls it. ``updated_at`` is app-maintained on every write (repo convention).
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
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot reach cover_jobs"
                )
            self._client = create_client(url, key)
        return self._client

    @guard("cover_jobs enqueue")
    async def enqueue(self, job: CoverJob) -> None:
        client = self._ensure_client()
        row: dict[str, object] = {
            "id": job.id,
            "user_id": job.user_id,
            "course_id": job.course_id,
            "status": CoverJobStatus.QUEUED.value,
            "style_preset": job.style_preset.value,
            "input_hash": job.input_hash,
            "config": job.config,
        }
        await asyncio.to_thread(lambda: client.table(_TABLE).insert(row).execute())  # type: ignore[attr-defined]

    @guard("cover_jobs claim")
    async def claim(self, *, worker_id: str) -> CoverJob | None:
        client = self._ensure_client()

        def _run() -> object:
            return client.rpc(_CLAIM_RPC, {"p_worker": worker_id}).execute()  # type: ignore[attr-defined]

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return CoverJob.model_validate(rows[0]) if rows else None

    @guard("cover_jobs heartbeat")
    async def heartbeat(self, *, job_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self._patch(job_id, {"claimed_at": now, "updated_at": now})

    @guard("cover_jobs update_status")
    async def update_status(self, *, job_id: str, status: CoverJobStatus) -> None:
        client = self._ensure_client()
        patch = {"status": status.value, "updated_at": datetime.now(UTC).isoformat()}

        # A 0-row update (settled/gone) is a deliberate no-op — a best-effort progress write must
        # never fail the render (@guard still surfaces a genuine backend error).
        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .update(patch)
                .eq("id", job_id)
                .not_.in_("status", list(_TERMINAL_STATUSES))
                .execute()
            )

        await asyncio.to_thread(_run)

    @guard("cover_jobs complete")
    async def complete(self, *, job_id: str) -> None:
        await self._settle(
            job_id,
            {
                "status": CoverJobStatus.READY.value,
                "error": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    @guard("cover_jobs fail")
    async def fail(self, *, job_id: str, error: str) -> None:
        await self._settle(
            job_id,
            {
                "status": CoverJobStatus.FAILED.value,
                "error": error,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    @guard("cover_jobs cancel")
    async def cancel(self, *, job_id: str, owner_id: str) -> bool:
        client = self._ensure_client()
        patch = {
            "status": CoverJobStatus.CANCELLED.value,
            "claimed_at": None,  # release the lease (terminal anyway)
            "claimed_by": None,
            "updated_at": datetime.now(UTC).isoformat(),
        }

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

    @guard("cover_jobs get")
    async def get(self, *, job_id: str, owner_id: str | None = None) -> CoverJob | None:
        client = self._ensure_client()

        def _run() -> object:
            query = client.table(_TABLE).select("*").eq("id", job_id)  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)
            return query.limit(1).execute()

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return CoverJob.model_validate(rows[0]) if rows else None

    @guard("cover_jobs find_active")
    async def find_active(self, *, course_id: str, owner_id: str) -> CoverJob | None:
        client = self._ensure_client()

        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("*")
                .eq("user_id", owner_id)
                .eq("course_id", course_id)
                .not_.in_("status", list(_TERMINAL_STATUSES))
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return CoverJob.model_validate(rows[0]) if rows else None

    @guard("cover_jobs find_latest_ready")
    async def find_latest_ready(self, *, course_id: str, owner_id: str) -> CoverJob | None:
        client = self._ensure_client()

        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("*")
                .eq("user_id", owner_id)
                .eq("course_id", course_id)
                .eq("status", CoverJobStatus.READY.value)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return CoverJob.model_validate(rows[0]) if rows else None

    @guard("cover_jobs sweep")
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

    @guard("cover_jobs list_for_course")
    async def list_for_course(self, *, course_id: str, owner_id: str) -> list[CoverJob]:
        client = self._ensure_client()

        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("*")
                .eq("user_id", owner_id)
                .eq("course_id", course_id)
                .execute()
            )

        response = await asyncio.to_thread(_run)
        return [CoverJob.model_validate(row) for row in (response.data or [])]

    @guard("cover_jobs delete_for_course")
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
        # zero-row no-op — the protocol contract is that job state is never silently wrong.
        def _run() -> object:
            return client.table(_TABLE).update(patch, count="exact").eq("id", job_id).execute()  # type: ignore[attr-defined]

        response = await asyncio.to_thread(_run)
        if not (getattr(response, "count", None) or 0):
            raise PersistenceError(f"cover job {job_id!r} not found")

    async def _settle(self, job_id: str, patch: dict[str, object]) -> None:
        """A terminal settle (complete/fail) that never overwrites a CANCELLED job — the owner's
        stop wins even if the render finished in the same instant. Zero rows ⇒ the job is gone OR
        already cancelled: a cancelled row is a benign no-op; a missing row is an error."""
        client = self._ensure_client()

        def _run() -> object:
            return (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .update(patch, count="exact")
                .eq("id", job_id)
                .neq("status", CoverJobStatus.CANCELLED.value)
                .execute()
            )

        response = await asyncio.to_thread(_run)
        if getattr(response, "count", None) or 0:
            return
        # Zero rows: tell a benign cancelled job (no-op) apart from a genuinely missing one (error).
        try:
            existing = await self.get(job_id=job_id)
        except PersistenceError:
            return
        if existing is not None and existing.status is CoverJobStatus.CANCELLED:
            return
        raise PersistenceError(f"cover job {job_id!r} not found")
