from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from .schema import LessonParts

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "live_materials"


class SupabaseMaterialStore:
    """The durable material store: one row per prefetched concept, ``jsonb`` payload, lazy
    service-role client — the knowledge store's shape (P2c T4).

    Durable rather than in-process (U3) because a 30-minute session outlives a deploy and may be
    served by more than one replica: material prefetched by one process has to be there for the
    request that consumes it, wherever that runs, and for the next session on the same map.
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
        self._client = client

    def _ensure_client(self) -> object:
        if self._client is None:
            self._client = supabase_client(
                url_env=self._url_env,
                service_key_env=self._service_key_env,
                purpose="persist materials",
            )
        return self._client

    @guard("live_materials upsert")
    def save(
        self, graph_id: str, node_id: str, parts: LessonParts, *, owner_id: str | None = None
    ) -> None:
        client = self._ensure_client()
        client.table(_TABLE).upsert(  # type: ignore[attr-defined]
            {
                "user_id": owner_id,
                "graph_id": graph_id,
                "node_id": node_id,
                "payload": parts.model_dump(mode="json", by_alias=True),
            },
            on_conflict="user_id,graph_id,node_id",
        ).execute()

    @guard("live_materials load")
    def load(self, graph_id: str, *, owner_id: str | None = None) -> dict[str, LessonParts]:
        client = self._ensure_client()
        query = client.table(_TABLE).select("node_id,payload").eq("graph_id", graph_id)  # type: ignore[attr-defined]
        # Constrained either way: the service-role client bypasses RLS, so an unscoped read must
        # match only unowned rows rather than seeing every learner's material.
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        rows = query.execute().data or []
        return {row["node_id"]: LessonParts.model_validate(row["payload"]) for row in rows}

    @guard("live_materials delete")
    def forget(self, graph_id: str, node_id: str, *, owner_id: str | None = None) -> None:
        client = self._ensure_client()
        query = (
            client.table(_TABLE)  # type: ignore[attr-defined]
            .delete()
            .eq("graph_id", graph_id)
            .eq("node_id", node_id)
        )
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        query.execute()
