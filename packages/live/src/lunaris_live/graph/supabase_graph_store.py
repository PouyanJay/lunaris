from datetime import UTC, datetime

from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from .graph_version_conflict_error import GraphVersionConflictError
from .schema import ConceptGraph

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "live_graphs"


class SupabaseGraphStore:
    """The durable concept-graph store: Supabase Postgres, ``jsonb`` payload, lazy service-role
    client.

    Mirrors Studio's ``SupabaseCourseStore`` — same lazy construction (so the composition root can
    build it without creds or network), same camelCase wire payload (what the web already consumes),
    same ``guard`` translation of driver failures into ``PersistenceError``.

    One deliberate difference: a graph is **mutable**. C1 grows it mid-session, so ``save`` upserts
    on ``id`` and the row records the current ``version``. The row is the head of the graph, not an
    immutable artifact.
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
                purpose="persist graphs",
            )
        return self._client

    @guard("live_graphs upsert")
    def save(
        self,
        graph: ConceptGraph,
        *,
        owner_id: str | None = None,
        expected_version: int | None = None,
    ) -> None:
        client = self._ensure_client()
        row: dict[str, object] = {
            "id": graph.graph_id,
            "topic": graph.topic,
            "version": graph.version,
            "payload": graph.model_dump(by_alias=True, mode="json"),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if owner_id is not None:
            # The compile writes through the service-role client (it bypasses RLS, because a compile
            # can outlive the caller's JWT), so isolation rides entirely on stamping the right
            # user_id here — that column is what RLS enforces against for any later user-JWT read.
            row["user_id"] = owner_id
        if expected_version is None:
            client.table(_TABLE).upsert(row).execute()  # type: ignore[attr-defined]
            return

        # Conditional on the version we read. Postgres decides the winner, so two extensions racing
        # from the same version cannot both succeed however the requests interleave above.
        # count="exact" rather than reading back rows — the house convention for "did my
        # conditional write actually land" (see supabase_cover_job_queue), because a zero-row
        # no-op must be loud rather than indistinguishable from a successful write.
        updated = (
            client.table(_TABLE)  # type: ignore[attr-defined]
            .update(row, count="exact")
            .eq("id", graph.graph_id)
            .eq("version", expected_version)
            .execute()
        )
        if not updated.count:
            raise GraphVersionConflictError(graph.graph_id)

    @guard("live_graphs select")
    def load(self, graph_id: str, *, owner_id: str | None = None) -> ConceptGraph:
        client = self._ensure_client()
        query = client.table(_TABLE).select("payload").eq("id", graph_id)  # type: ignore[attr-defined]
        # Constrain on the owner either way: an unscoped read matches only rows that are themselves
        # unowned, rather than seeing everything. Same rule as MemoryGraphStore — a store must not
        # depend on the auth wiring above it staying configured the way it is today.
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        rows = query.limit(1).execute().data
        if not rows:
            raise FileNotFoundError(graph_id)
        return ConceptGraph.model_validate(rows[0]["payload"])
