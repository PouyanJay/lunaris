from datetime import UTC, datetime, timedelta
from uuid import UUID

from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from ..registry.cache_key import sim_cache_key
from .schema.job import SimJob
from .schema.request import SimRequest


class SupabaseSimQueue:
    def __init__(self, *, client: object | None = None) -> None:
        self._client = client

    def _db(self) -> object:
        if self._client is None:
            self._client = supabase_client(
                url_env="SUPABASE_URL",
                service_key_env="SUPABASE_SERVICE_ROLE_KEY",
                purpose="queue live simulators",
            )
        return self._client

    @guard("enqueue live simulator")
    def enqueue(self, request: SimRequest, *, session_id: str, owner_id: str) -> str:
        return str(
            self._db()
            .rpc(
                "enqueue_live_sim",
                {  # type: ignore[attr-defined]
                    "p_owner": str(UUID(owner_id)),
                    "p_session": session_id,
                    "p_key": sim_cache_key(request.node, request.criterion),
                    "p_request": request.model_dump(mode="json", by_alias=True),
                },
            )
            .execute()
            .data
        )

    @guard("take live simulator")
    def take(self) -> SimJob | None:
        row = self._db().rpc("take_live_sim_request").execute().data  # type: ignore[attr-defined]
        if not row:
            return None
        return SimJob.model_validate(
            {key: row[key] for key in ("owner_id", "session_id", "cache_key", "token", "request")}
        )

    @guard("live simulator status")
    def status(self, cache_key: str, *, owner_id: str) -> str:
        owner = str(UUID(owner_id))
        rows = (
            self._db()
            .table("live_sim_builds")
            .select("status,expires_at")
            .eq(  # type: ignore[attr-defined]
                "owner_id", owner
            )
            .eq("cache_key", cache_key)
            .execute()
            .data
        )
        if rows:
            row = rows[0]
            if row["status"] == "building" and datetime.fromisoformat(
                row["expires_at"]
            ) <= datetime.now(UTC):
                return "indeterminate"
            return row["status"]
        return self._pending_status(cache_key, owner)

    def _pending_status(self, cache_key: str, owner: str) -> str:
        rows = (
            self._db()
            .table("live_sim_requests")
            .select("created_at")
            .eq(  # type: ignore[attr-defined]
                "owner_id", owner
            )
            .eq("cache_key", cache_key)
            .execute()
            .data
        )
        if rows and datetime.fromisoformat(rows[0]["created_at"]) > datetime.now(UTC) - timedelta(
            minutes=10
        ):
            return "queued"
        return "unavailable"
