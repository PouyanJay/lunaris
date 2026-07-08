import asyncio
import os
from datetime import datetime

from .learning_event import LearningEvent
from .store_unavailable_error import ActivityStoreUnavailableError

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_EVENTS_TABLE = "learning_events"
_MINUTES_TABLE = "study_minutes"


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event_from_row(row: dict) -> LearningEvent:
    return LearningEvent(
        event_type=row["event_type"],
        course_id=row["course_id"],
        course_title=row.get("course_title"),
        lesson_id=row.get("lesson_id"),
        lesson_title=row.get("lesson_title"),
        kc_id=row.get("kc_id"),
        kc_label=row.get("kc_label"),
        occurred_at=_parse_timestamp(row["occurred_at"]),
    )


class SupabaseActivityStore:
    """The production activity store: Supabase Postgres, lazy service-role client.

    Mirrors SupabaseProgressStore: the service-role client bypasses RLS (this API-layer store
    scopes every query by the authenticated ``user_id``), built lazily on first use so
    construction needs no creds. The tables are additionally owner-scoped by RLS, so a user-JWT
    client could only ever reach its own rows even if it queried directly. The synchronous
    supabase-py calls run off the event loop via ``asyncio.to_thread``.
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
                    f"{self._url_env} / {self._service_key_env} not set; cannot store activity"
                )
            self._client = create_client(url, key)
        return self._client

    @staticmethod
    def _require_user(user_id: str | None) -> str:
        # With Supabase configured, auth is configured — the API always resolves a real user.
        if user_id is None:
            raise RuntimeError("activity requires an authenticated user when Supabase is active")
        return user_id

    async def record_event(self, *, user_id: str | None, event: LearningEvent) -> None:
        owner = self._require_user(user_id)
        client = self._ensure_client()
        row = {
            "user_id": owner,
            "event_type": event.event_type,
            "course_id": event.course_id,
            "course_title": event.course_title,
            "lesson_id": event.lesson_id,
            "lesson_title": event.lesson_title,
            "kc_id": event.kc_id,
            "kc_label": event.kc_label,
            "occurred_at": event.occurred_at.isoformat(),
        }

        def _insert() -> object:
            return client.table(_EVENTS_TABLE).insert(row).execute()  # type: ignore[attr-defined]

        try:
            await asyncio.to_thread(_insert)
        except Exception as exc:
            raise ActivityStoreUnavailableError("activity backend unavailable") from exc

    async def record_minute(self, *, user_id: str | None, bucket_start: datetime) -> None:
        owner = self._require_user(user_id)
        client = self._ensure_client()
        row = {"user_id": owner, "bucket_start": bucket_start.isoformat()}

        def _upsert() -> object:
            return (
                client.table(_MINUTES_TABLE)  # type: ignore[attr-defined]
                .upsert(row, on_conflict="user_id,bucket_start")
                .execute()
            )

        try:
            await asyncio.to_thread(_upsert)
        except Exception as exc:
            raise ActivityStoreUnavailableError("activity backend unavailable") from exc

    async def events(self, *, user_id: str | None) -> list[LearningEvent]:
        owner = self._require_user(user_id)
        client = self._ensure_client()

        def _select() -> object:
            return (
                client.table(_EVENTS_TABLE)  # type: ignore[attr-defined]
                .select(
                    "event_type, course_id, course_title, lesson_id, lesson_title, kc_id,"
                    " kc_label, occurred_at"
                )
                .eq("user_id", owner)
                .order("occurred_at", desc=True)
                .execute()
            )

        try:
            response = await asyncio.to_thread(_select)
        except Exception as exc:
            raise ActivityStoreUnavailableError("activity backend unavailable") from exc
        return [_event_from_row(row) for row in response.data or []]  # type: ignore[attr-defined]

    async def minutes(self, *, user_id: str | None) -> list[datetime]:
        owner = self._require_user(user_id)
        client = self._ensure_client()

        def _select() -> object:
            return (
                client.table(_MINUTES_TABLE)  # type: ignore[attr-defined]
                .select("bucket_start")
                .eq("user_id", owner)
                .execute()
            )

        try:
            response = await asyncio.to_thread(_select)
        except Exception as exc:
            raise ActivityStoreUnavailableError("activity backend unavailable") from exc
        return [_parse_timestamp(row["bucket_start"]) for row in response.data or []]  # type: ignore[attr-defined]
