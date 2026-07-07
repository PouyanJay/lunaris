import asyncio
import os
from datetime import UTC, datetime

from .lesson_mark import LessonMark, LessonState
from .objective_mark import ObjectiveMark

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_OBJECTIVES_TABLE = "objective_progress"
_LESSONS_TABLE = "lesson_progress"


class SupabaseProgressStore:
    """The production progress store: Supabase Postgres, lazy service-role client.

    Mirrors SupabaseUserConfigStore: the service-role client bypasses RLS (this API-layer store
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
                    f"{self._url_env} / {self._service_key_env} not set; cannot store progress"
                )
            self._client = create_client(url, key)
        return self._client

    @staticmethod
    def _require_user(user_id: str | None) -> str:
        # With Supabase configured, auth is configured — the API always resolves a real user.
        if user_id is None:
            raise RuntimeError("progress requires an authenticated user when Supabase is active")
        return user_id

    async def _select(
        self, client: object, table: str, columns: str, *, owner: str, course_id: str
    ) -> list[dict]:
        response = await asyncio.to_thread(
            lambda: (
                client.table(table)  # type: ignore[attr-defined]
                .select(columns)
                .eq("user_id", owner)
                .eq("course_id", course_id)
                .execute()
            )
        )
        return response.data or []

    async def snapshot(
        self, *, user_id: str | None, course_id: str
    ) -> tuple[list[ObjectiveMark], list[LessonMark]]:
        owner = self._require_user(user_id)
        client = self._ensure_client()
        # The two reads are independent — fan out rather than paying two sequential round-trips.
        objective_rows, lesson_rows = await asyncio.gather(
            self._select(
                client,
                _OBJECTIVES_TABLE,
                "module_id, objective_index, understood_at",
                owner=owner,
                course_id=course_id,
            ),
            self._select(
                client,
                _LESSONS_TABLE,
                "lesson_id, state, updated_at",
                owner=owner,
                course_id=course_id,
            ),
        )
        objectives = [
            ObjectiveMark(
                course_id=course_id,
                module_id=row["module_id"],
                objective_index=row["objective_index"],
                understood_at=datetime.fromisoformat(row["understood_at"].replace("Z", "+00:00")),
            )
            for row in objective_rows
        ]
        lessons = [
            LessonMark(
                course_id=course_id,
                lesson_id=row["lesson_id"],
                state=row["state"],
                updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
            )
            for row in lesson_rows
        ]
        return objectives, lessons

    async def set_objective(
        self,
        *,
        user_id: str | None,
        course_id: str,
        module_id: str,
        objective_index: int,
        understood: bool,
    ) -> None:
        owner = self._require_user(user_id)
        key = {
            "user_id": owner,
            "course_id": course_id,
            "module_id": module_id,
            "objective_index": objective_index,
        }
        if understood:
            await self._upsert_objective(key)
        else:
            await self._delete_objective(key)

    async def _upsert_objective(self, key: dict) -> None:
        client = self._ensure_client()
        await asyncio.to_thread(
            lambda: (
                client.table(_OBJECTIVES_TABLE)  # type: ignore[attr-defined]
                .upsert(
                    {**key, "understood_at": datetime.now(UTC).isoformat()},
                    on_conflict="user_id,course_id,module_id,objective_index",
                )
                .execute()
            )
        )

    async def _delete_objective(self, key: dict) -> None:
        client = self._ensure_client()
        query = client.table(_OBJECTIVES_TABLE).delete()  # type: ignore[attr-defined]
        for column, value in key.items():
            query = query.eq(column, value)
        await asyncio.to_thread(query.execute)

    async def set_lesson(
        self, *, user_id: str | None, course_id: str, lesson_id: str, state: LessonState
    ) -> None:
        owner = self._require_user(user_id)
        client = self._ensure_client()
        await asyncio.to_thread(
            lambda: (
                client.table(_LESSONS_TABLE)  # type: ignore[attr-defined]
                .upsert(
                    {
                        "user_id": owner,
                        "course_id": course_id,
                        "lesson_id": lesson_id,
                        "state": state,
                        "updated_at": datetime.now(UTC).isoformat(),
                    },
                    on_conflict="user_id,course_id,lesson_id",
                )
                .execute()
            )
        )
