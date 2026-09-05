from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from .schema import LearnerModel, NodeKnowledge

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "live_knowledge"


class SupabaseKnowledgeStore:
    """The durable learner-model store: one row per concept the learner has evidence about.

    A row per concept rather than a document per map, unlike the session and graph stores. The write
    pattern is the reason: a turn produces evidence about exactly one concept, so a per-concept
    upsert touches one row where a document rewrite would rewrite the learner's whole history of the
    map on every answer. It also makes the reads P2b's mastery meters want ("this concept, across
    sessions") a lookup rather than a scan through a payload.
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
                purpose="persist knowledge",
            )
        return self._client

    @guard("live_knowledge upsert")
    def save(self, model: LearnerModel, *, owner_id: str | None = None) -> None:
        client = self._ensure_client()
        rows = [
            {
                "user_id": owner_id,
                "graph_id": model.graph_id,
                "node_id": known.node_id,
                "estimate": known.estimate,
                "evidence_count": known.evidence_count,
                "last_evidence_turn": known.last_evidence_turn,
                "prior": known.prior,
                "review_stage": known.review_stage,
                "due_at": known.due_at.isoformat() if known.due_at is not None else None,
            }
            for known in model.nodes.values()
        ]
        if not rows:
            # Nothing believed yet. Skipped rather than issued as an empty upsert, which some
            # PostgREST versions answer with a 400 — a first session must never fail on its own
            # emptiness.
            return
        client.table(_TABLE).upsert(  # type: ignore[attr-defined]
            rows, on_conflict="user_id,graph_id,node_id"
        ).execute()

    @guard("live_knowledge load")
    def load(self, graph_id: str, *, owner_id: str | None = None) -> LearnerModel:
        client = self._ensure_client()
        query = client.table(_TABLE).select("*").eq("graph_id", graph_id)  # type: ignore[attr-defined]
        # Constrained either way: the service-role client bypasses RLS, so an unscoped read must
        # match only unowned rows rather than seeing every learner's beliefs.
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        rows = query.execute().data or []
        return LearnerModel(
            graph_id=graph_id,
            nodes={
                row["node_id"]: NodeKnowledge(
                    node_id=row["node_id"],
                    estimate=row["estimate"],
                    evidence_count=row["evidence_count"],
                    last_evidence_turn=row["last_evidence_turn"],
                    # ``.get``: rows written before P2c T3 have no column value to read.
                    prior=row.get("prior"),
                    # And before T6, no schedule.
                    review_stage=row.get("review_stage", 0),
                    due_at=row.get("due_at"),
                )
                for row in rows
            },
        )

    @guard("live_knowledge forget")
    def forget(self, graph_id: str, *, owner_id: str | None = None) -> None:
        """Clear this owner's beliefs about one map (T5).

        Scoped in the DELETE itself and either way, for the reason ``load`` gives: the service-role
        client bypasses RLS, so this predicate is the only thing keeping a reset inside its own
        owner. Silent when nothing matched, unlike the session store's delete — "forget this" on a
        topic with nothing to forget has already happened, and a learner pressing it twice must not
        meet an error the second time.
        """
        client = self._ensure_client()
        query = client.table(_TABLE).delete().eq("graph_id", graph_id)  # type: ignore[attr-defined]
        query = query.is_("user_id", None) if owner_id is None else query.eq("user_id", owner_id)
        query.execute()
