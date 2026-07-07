import asyncio
import os
from datetime import UTC, datetime

from .store_protocol import LessonMark, LessonState, ObjectiveMark

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

    async def snapshot(
        self, *, user_id: str | None, course_id: str
    ) -> tuple[list[ObjectiveMark], list[LessonMark]]:
        owner = self._require_user(user_id)
        client = self._ensure_client()
        objectives_response = await asyncio.to_thread(
            lambda: (
                client.table(_OBJECTIVES_TABLE)  # type: ignore[attr-defined]
                .select("module_id, objective_index, understood_at")
                .eq("user_id", owner)
                .eq("course_id", course_id)
                .execute()
            )
        )
        lessons_response = await asyncio.to_thread(
            lambda: (
                client.table(_LESSONS_TABLE)  # type: ignore[attr-defined]
                .select("lesson_id, state, updated_at")
                .eq("user_id", owner)
                .eq("course_id", course_id)
                .execute()
            )
        )
        objectives = [
            ObjectiveMark(
                course_id=course_id,
                module_id=row["module_id"],
                objective_index=row["objective_index"],
                understood_at=datetime.fromisoformat(row["understood_at"]),
            )
            for row in objectives_response.data or []
        ]
        lessons = [
            LessonMark(
                course_id=course_id,
                lesson_id=row["lesson_id"],
                state=row["state"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in lessons_response.data or []
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
        client = self._ensure_client()
        if understood:
            await asyncio.to_thread(
                lambda: (
                    client.table(_OBJECTIVES_TABLE)  # type: ignore[attr-defined]
                    .upsert(
                        {
                            "user_id": owner,
                            "course_id": course_id,
                            "module_id": module_id,
                            "objective_index": objective_index,
                            "understood_at": datetime.now(UTC).isoformat(),
                        },
                        on_conflict="user_id,course_id,module_id,objective_index",
                    )
                    .execute()
                )
            )
        else:
            await asyncio.to_thread(
                lambda: (
                    client.table(_OBJECTIVES_TABLE)  # type: ignore[attr-defined]
                    .delete()
                    .eq("user_id", owner)
                    .eq("course_id", course_id)
                    .eq("module_id", module_id)
                    .eq("objective_index", objective_index)
                    .execute()
                )
            )

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
