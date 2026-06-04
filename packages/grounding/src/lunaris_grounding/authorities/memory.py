from collections.abc import Iterable

from lunaris_runtime.schema import SubjectField

from lunaris_grounding.authorities.authority import SourceAuthority


class InMemorySourceAuthorityStore:
    """An in-process source-authority config — the deterministic test/no-key backbone.

    Implements the same contract as the Supabase store over an in-memory dict keyed by the
    ``(domain, field)`` identity, so the scorer's tier-prior lookup + the management CRUD can be
    proven offline without a database. The no-key fallback (lost on restart); the durable, editable
    config requires Supabase.
    """

    def __init__(self, authorities: Iterable[SourceAuthority] = ()) -> None:
        self._by_key: dict[tuple[str, SubjectField | None], SourceAuthority] = {
            (a.domain, a.field): a for a in authorities
        }

    async def list_all(self) -> list[SourceAuthority]:
        return list(self._by_key.values())

    async def upsert(self, authority: SourceAuthority) -> None:
        self._by_key[(authority.domain, authority.field)] = authority

    async def delete(self, domain: str, field: SubjectField | None) -> bool:
        return self._by_key.pop((domain, field), None) is not None
