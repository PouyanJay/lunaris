import asyncio
import os
from datetime import UTC, datetime

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "user_runtime_config"
_PK = "user_id,config_key"


class SupabaseUserConfigStore:
    """The production per-user config store: Supabase Postgres, lazy service-role client.

    Mirrors the runtime Supabase stores — the service-role client bypasses RLS (the build path reads
    a user's config as a background task that can outlive their JWT), built lazily on first use so
    construction needs no creds and no network. The synchronous supabase-py calls run off the event
    loop via ``asyncio.to_thread``. Values are non-secret (model ids), so no encryption — unlike the
    credential store. The ``user_runtime_config`` table is owner-scoped RLS, so a user-JWT client
    can only ever reach its own rows even if it queried directly.
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
                    f"{self._url_env} / {self._service_key_env} not set; cannot store config"
                )
            self._client = create_client(url, key)
        return self._client

    async def get_all(self, *, user_id: str) -> dict[str, str]:
        client = self._ensure_client()
        response = await asyncio.to_thread(
            lambda: (
                client.table(_TABLE)  # type: ignore[attr-defined]
                .select("config_key, config_value")
                .eq("user_id", user_id)
                .execute()
            )
        )
        rows = response.data or []
        return {str(row["config_key"]): str(row["config_value"]) for row in rows}

    async def set(self, *, user_id: str, key: str, value: str) -> None:
        client = self._ensure_client()
        row = {
            "user_id": user_id,
            "config_key": key,
            "config_value": value,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        # Upsert on the composite PK so re-setting a key overwrites the value in place.
        await asyncio.to_thread(
            lambda: client.table(_TABLE).upsert(row, on_conflict=_PK).execute()  # type: ignore[attr-defined]
        )
