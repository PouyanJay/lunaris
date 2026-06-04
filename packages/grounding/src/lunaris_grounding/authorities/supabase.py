import asyncio
import os

import structlog
from lunaris_runtime.resilience import retry_on_rate_limit
from lunaris_runtime.schema import AuthorityKind, SourceType, SubjectField, TrustTier

from lunaris_grounding.authorities.authority import SourceAuthority

logger = structlog.get_logger()

_URL_ENV = "SUPABASE_URL"
_SERVICE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
_TABLE = "source_authorities"
_COLS = "domain,kind,field,tier,source_type,note"
# The table's unique identity, for upsert conflict resolution. NULLS NOT DISTINCT (the migration) is
# what makes a global (field IS NULL) row a single addressable key here.
_CONFLICT_KEY = "domain,field"


class SupabaseSourceAuthorityStore:
    """The production source-authority config: the editable ``source_authorities`` table (P6.2).

    Mirrors ``SupabaseCorpusStore`` — a lazy service-role client (no creds/network at construction;
    a pre-built ``client`` may be injected as the test seam), each sync call run off the event loop
    via ``asyncio.to_thread``, and reads wrapped in the rate-limit retry. Server-only: RLS is on
    with no policies, so only the backend service-role client (which bypasses RLS) sees the rows.
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
                    f"{self._url_env} / {self._service_key_env} not set; cannot reach authorities"
                )
            self._client = create_client(url, key)
        return self._client

    async def list_all(self) -> list[SourceAuthority]:
        client = self._ensure_client()
        response = await retry_on_rate_limit(
            lambda: asyncio.to_thread(
                lambda: client.table(_TABLE).select(_COLS).execute()  # type: ignore[attr-defined]
            )
        )
        return _authorities_from_rows(response.data or [])

    async def upsert(self, authority: SourceAuthority) -> None:
        client = self._ensure_client()
        row = {
            "domain": authority.domain,
            "kind": authority.kind.value,
            "field": authority.field.value if authority.field is not None else None,
            "tier": authority.trust_tier.value,
            "source_type": authority.source_type.value if authority.source_type else None,
            "note": authority.note,
        }
        await retry_on_rate_limit(
            lambda: asyncio.to_thread(
                lambda: client.table(_TABLE).upsert(row, on_conflict=_CONFLICT_KEY).execute()  # type: ignore[attr-defined]
            )
        )

    async def delete(self, domain: str, field: SubjectField | None) -> bool:
        client = self._ensure_client()

        def _run() -> object:
            query = client.table(_TABLE).delete(count="exact").eq("domain", domain)  # type: ignore[attr-defined]
            # A global row has field IS NULL; PostgREST needs is_(None), not eq(None).
            query = query.is_("field", "null") if field is None else query.eq("field", field.value)
            return query.execute()

        response = await retry_on_rate_limit(lambda: asyncio.to_thread(_run))
        return int(getattr(response, "count", 0) or 0) > 0


def _authorities_from_rows(rows: list[dict[str, object]]) -> list[SourceAuthority]:
    """Map table rows to authorities, dropping any malformed row (a corrupt enum, a missing domain)
    rather than crashing the whole config read — one bad row degrades coverage, not the build."""
    authorities: list[SourceAuthority] = []
    for row in rows:
        authority = _authority_from_row(row)
        if authority is not None:
            authorities.append(authority)
    return authorities


def _authority_from_row(row: dict[str, object]) -> SourceAuthority | None:
    domain = row.get("domain")
    kind = _as_enum(AuthorityKind, row.get("kind"))
    tier = _as_enum(TrustTier, row.get("tier"))
    if not isinstance(domain, str) or kind is None or tier is None:
        logger.warning("source_authority_row_invalid", domain=domain)
        return None
    raw_note = row.get("note")
    try:
        return SourceAuthority(
            domain=domain,
            kind=kind,
            trust_tier=tier,
            field=_as_enum(SubjectField, row.get("field")),
            source_type=_as_enum(SourceType, row.get("source_type")),
            note=raw_note if isinstance(raw_note, str) else None,
        )
    except ValueError:
        # A field/kind mismatch (e.g. a PACK row missing its field) fails the model invariant; skip
        # it like any other corrupt row rather than taking down the config read.
        logger.warning("source_authority_row_inconsistent", domain=domain)
        return None


def _as_enum[E: (AuthorityKind, TrustTier, SourceType, SubjectField)](
    enum_cls: type[E], value: object
) -> E | None:
    if not isinstance(value, str):
        return None
    try:
        return enum_cls(value)
    except ValueError:
        return None
