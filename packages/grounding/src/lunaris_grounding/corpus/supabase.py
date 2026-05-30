import asyncio
import os

from lunaris_runtime.resilience import retry_on_rate_limit
from lunaris_runtime.schema import Citation

from lunaris_grounding.corpus.document import GroundingDocument
from lunaris_grounding.evidence import Evidence

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "grounding_documents"
_MATCH_FN = "match_grounding_documents"


class SupabaseCorpusStore:
    """The production corpus backend: Supabase pgvector (D2), lazy service-role client.

    Reads go through the ``match_grounding_documents`` RPC (cosine similarity in the DB);
    writes upsert into the ``grounding_documents`` table. The supabase-py client is
    synchronous, so each call is run off the event loop via ``asyncio.to_thread``. The
    client is built lazily on first use, so construction needs no creds and no network.
    """

    def __init__(self, *, url_env: str = _URL_ENV, service_key_env: str = _SERVICE_KEY_ENV) -> None:
        self._url_env = url_env
        self._service_key_env = service_key_env
        self._client: object | None = None

    def _ensure_client(self) -> object:
        if self._client is None:
            from supabase import create_client

            url = os.environ.get(self._url_env)
            key = os.environ.get(self._service_key_env)
            if not url or not key:
                raise RuntimeError(
                    f"{self._url_env} / {self._service_key_env} not set; cannot reach the corpus"
                )
            self._client = create_client(url, key)
        return self._client

    async def upsert(self, documents: list[GroundingDocument]) -> int:
        if not documents:
            return 0
        client = self._ensure_client()
        rows = [
            {
                "id": document.id,
                "kc_id": document.kc_id,
                "content": document.content,
                "title": document.title,
                "url": document.url,
                "run_id": document.run_id,
                "embedding": list(document.embedding),
            }
            for document in documents
        ]
        await retry_on_rate_limit(
            lambda: asyncio.to_thread(lambda: client.table(_TABLE).upsert(rows).execute())  # type: ignore[attr-defined]
        )
        return len(rows)

    async def match(
        self,
        embedding: list[float],
        *,
        k: int = 5,
        min_score: float = 0.0,
        kc_id: str | None = None,
    ) -> list[Evidence]:
        client = self._ensure_client()
        # The RPC treats a NULL kc_filter as "no KC filter"; make that contract explicit by
        # only sending the key when a KC is actually requested.
        params: dict[str, object] = {"query_embedding": embedding, "match_count": k}
        if kc_id is not None:
            params["kc_filter"] = kc_id
        response = await retry_on_rate_limit(
            lambda: asyncio.to_thread(lambda: client.rpc(_MATCH_FN, params).execute())  # type: ignore[attr-defined]
        )
        evidence: list[Evidence] = []
        for row in response.data or []:
            score = float(row["similarity"])
            if score < min_score:
                continue
            citation = Citation(
                id=str(row["id"]),
                title=row.get("title"),
                url=row.get("url"),
                snippet=row.get("content"),
            )
            evidence.append(Evidence(citation=citation, score=score))
        return evidence
