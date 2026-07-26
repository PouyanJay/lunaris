import asyncio
import os
from collections.abc import Sequence

import structlog

from lunaris_runtime.schema import CostEvent, CostPocket, CostProvider

from .guard import guard

logger = structlog.get_logger()

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "cost_events"

# PostgREST caps a single request at 1000 rows, so a long build's ledger is read in pages — else the
# drill-through / rollup recompute only ever sees the first 1000 events. The recorder's per-run cap
# bounds the total, so pagination terminates in a handful of pages.
_PAGE_SIZE = 1000
# A hard ceiling so a future cap change can't loop unbounded.
_MAX_PAGES = 20


class SupabaseCostEventStore:
    """The production build-cost ledger: Supabase Postgres, lazy service-role client.

    The cost twin of ``SupabaseRunEventStore``: append-only rows, one per paid call. All access
    goes through the service-role client, which bypasses RLS (the table is RLS-enabled with
    owner-only SELECT — server-write / owner-read). The supabase-py client is synchronous, so each
    call runs off the event loop via ``asyncio.to_thread``. The client is built lazily on first
    use, so construction needs no creds and no network.

    ``id`` and ``created_at`` are owned by the DB (identity / ``default now()``); the caller
    supplies the run-scoped ``seq`` and the calculated ``amount`` + ``price_book_version``.
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
        # An injected client (tests) skips lazy construction; production leaves it None.
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot record build costs"
                )
            self._client = create_client(url, key)
        return self._client

    @guard("cost_events insert")
    async def append(self, *, events: Sequence[CostEvent], owner_id: str | None = None) -> None:
        if not events:
            return  # an empty flush must never issue a no-op insert
        client = self._ensure_client()
        rows = [
            {
                "run_id": event.run_id,
                "course_id": event.course_id,
                "seq": event.seq,
                "component": event.component,
                "provider": event.provider.value,
                "model": event.model,
                "pocket": event.pocket.value,
                "usage": event.usage,
                "amount": event.amount,
                "currency": event.currency,
                "price_book_version": event.price_book_version,
                # Stamp the owner so RLS enforces for any later user-JWT client (the build writes
                # via service-role, which bypasses RLS).
                **({"user_id": owner_id} if owner_id is not None else {}),
            }
            for event in events
        ]
        await asyncio.to_thread(lambda: client.table(_TABLE).insert(rows).execute())  # type: ignore[attr-defined]

    @guard("cost_events list")
    async def list_for_course(
        self, *, course_id: str, owner_id: str | None = None
    ) -> list[CostEvent]:
        client = self._ensure_client()
        rows: list[dict[str, object]] = []
        for page_index in range(_MAX_PAGES):
            start = page_index * _PAGE_SIZE
            end = start + _PAGE_SIZE - 1

            def _run(s: int = start, e: int = end) -> object:
                query = client.table(_TABLE).select("*").eq("course_id", course_id)  # type: ignore[attr-defined]
                if owner_id is not None:
                    query = query.eq("user_id", owner_id)  # another user's ledger reads as empty
                return query.order("run_id").order("seq").range(s, e).execute()

            response = await asyncio.to_thread(_run)
            page = response.data or []
            rows.extend(page)
            if len(page) < _PAGE_SIZE:  # a short (or empty) page is the last one
                break
        else:
            logger.warning(
                "cost_events_read_hit_page_ceiling", course_id=course_id, pages=_MAX_PAGES
            )
        return [self._to_cost_event(row) for row in rows]

    @guard("cost_events delete")
    async def delete_for_course(self, *, course_id: str, owner_id: str | None = None) -> int:
        client = self._ensure_client()

        def _run() -> object:
            query = client.table(_TABLE).delete(count="exact").eq("course_id", course_id)  # type: ignore[attr-defined]
            if owner_id is not None:
                query = query.eq("user_id", owner_id)  # only purge the caller's own events
            return query.execute()

        response = await asyncio.to_thread(_run)
        return response.count or 0

    @staticmethod
    def _to_cost_event(row: dict[str, object]) -> CostEvent:
        # Coerce explicitly: supabase-py rows are untyped. The jsonb usage arrives as a fresh dict.
        return CostEvent(
            run_id=str(row["run_id"]),
            course_id=str(row["course_id"]),
            seq=int(row["seq"]),  # type: ignore[arg-type]
            component=str(row["component"]),
            provider=CostProvider(row["provider"]),
            model=str(row["model"]) if row.get("model") is not None else None,
            pocket=CostPocket(row["pocket"]),
            usage=row["usage"],  # type: ignore[arg-type]
            amount=float(row["amount"]),  # type: ignore[arg-type]
            currency=str(row["currency"]),
            price_book_version=str(row["price_book_version"]),
        )
