from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from .models.claim import GraphClaim
from .models.mutation import SessionMutation


class SupabaseGraphTransactions:
    def __init__(self, *, client: object | None = None) -> None:
        self._client = client

    def _db(self) -> object:
        if self._client is None:
            self._client = supabase_client(
                url_env="SUPABASE_URL",
                service_key_env="SUPABASE_SERVICE_ROLE_KEY",
                purpose="coordinate Live sessions",
            )
        return self._client

    def _args(self, claim: GraphClaim) -> dict:
        return {"p_owner": claim.owner_id, "p_graph": claim.graph_id, "p_token": claim.token}

    @guard("live graph acquire")
    def acquire(self, graph_id: str, *, owner_id: str | None) -> GraphClaim | None:
        token = (
            self._db()
            .rpc(  # type: ignore[attr-defined]
                "acquire_live_graph", {"p_owner": owner_id, "p_graph": graph_id}
            )
            .execute()
            .data
        )
        return GraphClaim(graph_id, owner_id, str(token)) if token else None

    @guard("live graph renew")
    def renew(self, claim: GraphClaim) -> bool:
        return bool(self._db().rpc("renew_live_graph", self._args(claim)).execute().data)  # type: ignore[attr-defined]

    @guard("live graph paid admission")
    def paid(self, claim: GraphClaim, operation_key: str) -> bool:
        args = {**self._args(claim), "p_operation": operation_key}
        return bool(self._db().rpc("begin_live_paid_operation", args).execute().data)  # type: ignore[attr-defined]

    @guard("live graph atomic commit")
    def commit(self, claim: GraphClaim, mutation: SessionMutation) -> None:
        payload = {
            "session": mutation.session.model_dump(mode="json", by_alias=True)
            if mutation.session
            else None,
            "knowledge": mutation.knowledge.model_dump(mode="json", by_alias=True)
            if mutation.knowledge
            else None,
            "expected_turns": mutation.expected_turns,
            "create": mutation.create,
            "delete_session": mutation.delete_session,
            "forget": mutation.forget,
        }
        self._db().rpc(  # type: ignore[attr-defined]
            "commit_live_graph", {**self._args(claim), "p_change": payload}
        ).execute()

    @guard("live graph release")
    def release(self, claim: GraphClaim) -> None:
        self._db().rpc("release_live_graph", self._args(claim)).execute()  # type: ignore[attr-defined]
