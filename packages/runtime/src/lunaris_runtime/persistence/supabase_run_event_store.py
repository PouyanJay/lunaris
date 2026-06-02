import asyncio
import os
from collections.abc import Sequence

from lunaris_runtime.schema import RunEvent, RunEventKind

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "run_events"


class SupabaseRunEventStore:
    """The production build-event log: Supabase Postgres, lazy service-role client.

    The append-only sibling of ``SupabaseRunStore`` — where that keeps one row per build, this keeps
    the full streamed transcript for replay. All access goes through the service-role client, which
    bypasses RLS (the table is RLS-enabled with no policies — server-only). The supabase-py client
    is synchronous, so each call runs off the event loop via ``asyncio.to_thread``. It is built
    lazily on first use, so construction needs no creds and no network (the composition root builds
    this unconditionally and only the first real write requires the environment).

    ``id`` and ``created_at`` are owned by the DB (``gen_random_uuid()`` / ``default now()``); the
    caller supplies the run-scoped ``seq`` that orders replay.
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
                    f"{self._url_env} / {self._service_key_env} not set; cannot record build events"
                )
            self._client = create_client(url, key)
        return self._client

    async def append(self, *, events: Sequence[RunEvent]) -> None:
        if not events:
            return  # an empty flush must never issue a no-op insert
        client = self._ensure_client()
        rows = [
            {
                "run_id": event.run_id,
                "course_id": event.course_id,
                "seq": event.seq,
                "kind": event.kind.value,
                "payload": event.payload,
            }
            for event in events
        ]
        await asyncio.to_thread(lambda: client.table(_TABLE).insert(rows).execute())  # type: ignore[attr-defined]

    async def list_for_run(self, *, run_id: str) -> list[RunEvent]:
        client = self._ensure_client()
        response = await asyncio.to_thread(
            lambda: (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("*")
                .eq("run_id", run_id)
                .order("seq")
                .execute()
            )
        )
        return [self._to_run_event(row) for row in (response.data or [])]

    async def delete_for_course(self, *, course_id: str) -> int:
        client = self._ensure_client()
        # Ask PostgREST for an exact count so the "how many were deleted?" answer doesn't depend on
        # the client's implicit return-representation default (which could change to minimal).
        response = await asyncio.to_thread(
            lambda: (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .delete(count="exact")
                .eq("course_id", course_id)
                .execute()
            )
        )
        return response.count or 0

    @staticmethod
    def _to_run_event(row: dict[str, object]) -> RunEvent:
        # Coerce explicitly: supabase-py rows are untyped. The jsonb payload arrives as a fresh dict
        # (parsed per response, shared with nothing) and kind as the stored string value.
        return RunEvent(
            run_id=str(row["run_id"]),
            course_id=str(row["course_id"]),
            seq=int(row["seq"]),  # type: ignore[arg-type]
            kind=RunEventKind(row["kind"]),
            payload=row["payload"],  # type: ignore[arg-type]
        )
