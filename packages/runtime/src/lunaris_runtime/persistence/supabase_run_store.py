import asyncio
import os
from datetime import UTC, datetime

from lunaris_runtime.schema import CourseRun, RunStatus

from .guard import guard

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "course_runs"


class SupabaseRunStore:
    """The production run-history index: Supabase Postgres, lazy service-role client.

    All access goes through the service-role client, which bypasses RLS (the table is RLS-enabled
    with no policies — server-only). The supabase-py client is synchronous, so each call runs off
    the event loop via ``asyncio.to_thread``. The client is built lazily on first use, so
    construction needs no creds and no network (the composition root can build this unconditionally
    and only the first real call requires the environment).

    ``created_at`` is owned by the DB (``default now()``); ``updated_at`` is stamped on ``finish``.
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
        # An injected client (tests) skips lazy construction; production leaves it None so the
        # service-role client is built from the environment on first use.
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot record run history"
                )
            self._client = create_client(url, key)
        return self._client

    @guard("course_runs upsert")
    async def start(
        self, *, run_id: str, course_id: str, topic: str, owner_id: str | None = None
    ) -> None:
        client = self._ensure_client()
        # Upsert so a retried run with the same course_id refreshes the row rather than 409-ing.
        row: dict[str, object] = {
            "id": course_id,
            "run_id": run_id,
            "topic": topic,
            "status": RunStatus.RUNNING.value,
        }
        if owner_id is not None:
            row["user_id"] = owner_id  # stamp the owner (Phase 2) — see SupabaseCourseStore.save
        await asyncio.to_thread(lambda: client.table(_TABLE).upsert(row).execute())  # type: ignore[attr-defined]

    @guard("course_runs update")
    async def finish(
        self,
        *,
        course_id: str,
        status: RunStatus,
        kc_count: int,
        module_count: int,
        owner_id: str | None = None,
    ) -> None:
        client = self._ensure_client()
        patch = {
            "status": status.value,
            "kc_count": kc_count,
            "module_count": module_count,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        def _run() -> object:
            query = client.table(_TABLE).update(patch).eq("id", course_id)  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # only finish a row the caller owns
            return query.execute()

        await asyncio.to_thread(_run)

    @guard("course_runs list")
    async def list_recent(self, *, limit: int = 50, owner_id: str | None = None) -> list[CourseRun]:
        client = self._ensure_client()

        def _run() -> object:
            query = client.table(_TABLE).select("*")  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # the sidebar shows only the caller's runs
            return query.order("created_at", desc=True).limit(limit).execute()

        response = await asyncio.to_thread(_run)
        return [self._to_course_run(row) for row in (response.data or [])]

    @guard("course_runs get")
    async def get(self, *, course_id: str, owner_id: str | None = None) -> CourseRun | None:
        client = self._ensure_client()

        def _run() -> object:
            query = client.table(_TABLE).select("*").eq("id", course_id)  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)
            return query.limit(1).execute()

        response = await asyncio.to_thread(_run)
        rows = response.data or []
        return self._to_course_run(rows[0]) if rows else None

    @guard("course_runs delete")
    async def delete(self, *, course_id: str, owner_id: str | None = None) -> bool:
        client = self._ensure_client()

        # Ask PostgREST for an exact count so the "did anything get deleted?" answer doesn't depend
        # on the client's implicit return-representation default (which could change to minimal).
        def _run() -> object:
            query = client.table(_TABLE).delete(count="exact").eq("id", course_id)  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # only the owner can delete their run row
            return query.execute()

        response = await asyncio.to_thread(_run)
        return (response.count or 0) > 0

    @staticmethod
    def _to_course_run(row: dict[str, object]) -> CourseRun:
        # Coerce explicitly: the supabase-py rows are untyped, and timestamptz arrives as an ISO
        # string the DB owns — parse it here rather than leaning on Pydantic's implicit coercion.
        return CourseRun(
            id=str(row["id"]),
            run_id=str(row["run_id"]),
            topic=str(row["topic"]),
            status=RunStatus(row["status"]),
            kc_count=int(row.get("kc_count", 0)),  # type: ignore[arg-type]
            module_count=int(row.get("module_count", 0)),  # type: ignore[arg-type]
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )
