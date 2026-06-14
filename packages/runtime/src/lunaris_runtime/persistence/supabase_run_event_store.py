import asyncio
import os
from collections.abc import Sequence

import structlog

from lunaris_runtime.schema import RunEvent, RunEventKind

from .guard import guard

logger = structlog.get_logger()

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "run_events"

# Supabase/PostgREST caps a single request at 1000 rows, so a long (or loopy) build's log has to be
# read in pages — else the replay only ever sees the first 1000 events and shows the build stuck
# mid-stream. The per-run write cap (RunEventRecorder.CAP_PER_RUN = 5000, in apps/api) bounds the
# total, so pagination terminates in at most ~6 pages on the largest run.
_PAGE_SIZE = 1000
# A hard ceiling so a future cap change (or a pathological full-page stream) can't loop unbounded.
_MAX_PAGES = 20


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

    @guard("run_events insert")
    async def append(self, *, events: Sequence[RunEvent], owner_id: str | None = None) -> None:
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
                # Stamp the owner (Phase 2) — the build writes via service-role, so the right
                # user_id here is what lets RLS enforce for any later user-JWT client.
                **({"user_id": owner_id} if owner_id is not None else {}),
            }
            for event in events
        ]
        await asyncio.to_thread(lambda: client.table(_TABLE).insert(rows).execute())  # type: ignore[attr-defined]

    @guard("run_events latest seq")
    async def latest_seq(self, *, run_id: str, owner_id: str | None = None) -> int | None:
        """The run's highest ``seq`` (one row, ``order(seq).desc().limit(1)``), or ``None`` if it
        has none — the seed a re-claimed worker continues from so its events never collide with a
        prior attempt's under the UNIQUE ``(run_id, seq)`` index."""
        client = self._ensure_client()

        def _run() -> object:
            query = client.table(_TABLE).select("seq").eq("run_id", run_id)  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # another user's transcript reads as empty
            return query.order("seq", desc=True).limit(1).execute()

        response = await asyncio.to_thread(_run)
        rows = response.data or []  # type: ignore[attr-defined]
        return int(rows[0]["seq"]) if rows else None

    @guard("run_events list")
    async def list_for_run(self, *, run_id: str, owner_id: str | None = None) -> list[RunEvent]:
        client = self._ensure_client()
        rows: list[dict[str, object]] = []
        for page_index in range(_MAX_PAGES):
            start = page_index * _PAGE_SIZE
            end = start + _PAGE_SIZE - 1

            def _run(s: int = start, e: int = end) -> object:
                query = client.table(_TABLE).select("*").eq("run_id", run_id)  # type: ignore[attr-defined]
                if owner_id is not None:
                    query = query.eq(
                        "user_id", owner_id
                    )  # another user's transcript reads as empty
                return query.order("seq").range(s, e).execute()

            response = await asyncio.to_thread(_run)
            page = response.data or []
            rows.extend(page)
            if len(page) < _PAGE_SIZE:  # a short (or empty) page is the last one
                break
        else:
            # Reached the page ceiling without a short page — surface it; the log is read truncated.
            logger.warning("run_events_read_hit_page_ceiling", run_id=run_id, pages=_MAX_PAGES)
        return [self._to_run_event(row) for row in rows]

    @guard("run_events delete")
    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int:
        client = self._ensure_client()

        # Ask PostgREST for an exact count so the "how many were deleted?" answer doesn't depend on
        # the client's implicit return-representation default (which could change to minimal).
        def _run() -> object:
            query = client.table(_TABLE).delete(count="exact").eq("course_id", course_id)  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # only purge the caller's own events
            return query.execute()

        response = await asyncio.to_thread(_run)
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
