from dataclasses import asdict

from lunaris_runtime.persistence import supabase_client
from lunaris_runtime.persistence.guard import guard

from ..models.snapshot_key import SnapshotKey
from ..schemas.snapshot import CorpusSnapshot


class SupabaseCorpusSnapshotStore:
    """Private immutable snapshots: no browser role may read embedded assessment keys."""

    def __init__(
        self,
        *,
        url_env: str = "SUPABASE_URL",
        service_key_env: str = "SUPABASE_SERVICE_ROLE_KEY",
        client: object | None = None,
    ) -> None:
        self._url_env = url_env
        self._service_key_env = service_key_env
        self._client = client

    def _table(self) -> object:
        if self._client is None:
            self._client = supabase_client(
                url_env=self._url_env,
                service_key_env=self._service_key_env,
                purpose="persist corpus snapshots",
            )
        return self._client.table("live_corpus_snapshots")  # type: ignore[attr-defined]

    @guard("corpus snapshot insert")
    def save(self, snapshot: CorpusSnapshot, *, owner_id: str) -> CorpusSnapshot:
        if not owner_id:
            raise FileNotFoundError("Owner required")
        key = SnapshotKey(
            owner_id=owner_id,
            course_id=snapshot.source.course_id,
            digest=snapshot.source.digest,
            adapter_version=snapshot.source.adapter_version,
            schema_version=snapshot.schema_version,
        )
        self._table().upsert(  # type: ignore[attr-defined]
            {**asdict(key), "payload": snapshot.model_dump(mode="json", by_alias=True)},
            on_conflict="owner_id,course_id,digest,adapter_version,schema_version",
            ignore_duplicates=True,
        ).execute()
        return self.load(key)

    @guard("corpus snapshot select")
    def load(self, key: SnapshotKey) -> CorpusSnapshot:
        if not key.owner_id:
            raise FileNotFoundError("Owner required")
        query = self._table().select("payload")  # type: ignore[attr-defined]
        for column, value in asdict(key).items():
            query = query.eq(column, value)
        rows = query.limit(1).execute().data
        if not rows:
            raise FileNotFoundError(key.course_id)
        return CorpusSnapshot.model_validate(rows[0]["payload"])
