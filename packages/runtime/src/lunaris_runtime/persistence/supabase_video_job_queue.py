import asyncio
import os
from datetime import UTC, datetime

from lunaris_runtime.schema import VideoJob, VideoJobStatus

from .guard import guard
from .persistence_error import PersistenceError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "video_jobs"
_CLAIM_RPC = "claim_video_job"


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

    @guard("video_jobs complete")
    async def complete(self, *, job_id: str) -> None:
        await self._patch(
            job_id,
            {
                "status": VideoJobStatus.READY.value,
                "error": None,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    @guard("video_jobs fail")
    async def fail(self, *, job_id: str, error: str) -> None:
        await self._patch(
            job_id,
            {
                "status": VideoJobStatus.FAILED.value,
                "error": error,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

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
