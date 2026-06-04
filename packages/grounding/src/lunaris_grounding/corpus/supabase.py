import asyncio
import os
from enum import Enum

import structlog
from lunaris_runtime.resilience import retry_on_rate_limit
from lunaris_runtime.schema import Citation
from pydantic import ValidationError

from lunaris_grounding.corpus.document import GroundingDocument
from lunaris_grounding.evidence import Evidence

logger = structlog.get_logger()


def _enum_value(member: Enum | None) -> str | None:
    return member.value if member is not None else None


_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "grounding_documents"
_MATCH_FN = "match_grounding_documents"


class SupabaseCorpusStore:
    """The production corpus backend: Supabase pgvector (D2), lazy service-role client.

    Reads go through the ``match_grounding_documents`` RPC (cosine similarity in the DB);
    writes upsert into the ``grounding_documents`` table. The supabase-py client is
    synchronous, so each call is run off the event loop via ``asyncio.to_thread``. The
    client is built lazily on first use, so construction needs no creds and no network; a
    pre-built ``client`` may be injected (the test seam — no creds, no network, no reach-in).

    Scope params (``kc_filter`` / ``course_filter``) are omitted rather than sent as ``None`` so a
    call resolves against the RPC's defaulted filters — and the pre-P6.0 3-arg signature too.
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
                # The DB columns are plain text, not jsonb — serialise each enum to its .value.
                "source_type": _enum_value(document.source_type),
                "trust_tier": _enum_value(document.trust_tier),
                "credibility": document.credibility,
                "fetched_at": document.fetched_at,
                "acquisition_mode": _enum_value(document.acquisition_mode),
                "course_id": document.course_id,
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
        course_id: str | None = None,
    ) -> list[Evidence]:
        client = self._ensure_client()
        # Omit an unset filter rather than sending None (see the class docstring for why).
        params: dict[str, object] = {"query_embedding": embedding, "match_count": k}
        if kc_id is not None:
            params["kc_filter"] = kc_id
        if course_id is not None:
            params["course_filter"] = course_id
        response = await retry_on_rate_limit(
            lambda: asyncio.to_thread(lambda: client.rpc(_MATCH_FN, params).execute())  # type: ignore[attr-defined]
        )
        evidence: list[Evidence] = []
        for row in response.data or []:
            score = float(row["similarity"])
            if score < min_score:
                continue
            evidence.append(Evidence(citation=_citation_from_row(row), score=score))
        return evidence


def _citation_from_row(row: dict[str, object]) -> Citation:
    """Map an RPC row to a Citation, degrading gracefully on a bad trust column.

    Read defensively: against an un-migrated RPC the trust columns are simply absent (→ None). And
    if a column is present but holds an out-of-vocabulary value (a corrupt or out-of-band DB write),
    a malformed trust field must not crash the whole retrieval — drop it to None and keep the
    citation, so one bad row degrades coverage rather than failing the claim's grounding.
    """
    base: dict[str, object | None] = {
        "id": str(row["id"]),
        "title": row.get("title"),
        "url": row.get("url"),
        "snippet": row.get("content"),
    }
    # Only the trust fields can fail validation (an out-of-vocab enum), so build them outside the
    # try — the fallback drops exactly them and keeps the base citation, never re-failing on base.
    trust_fields = {
        "trust_tier": row.get("trust_tier"),
        "credibility": row.get("credibility"),
        "source_type": row.get("source_type"),
        "fetched_at": row.get("fetched_at"),
    }
    try:
        return Citation(**base, **trust_fields)
    except ValidationError:
        logger.warning("corpus_row_trust_fields_invalid", row_id=base["id"])
        return Citation(**base)
