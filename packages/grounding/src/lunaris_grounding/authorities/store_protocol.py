from typing import Protocol

from lunaris_runtime.schema import SubjectField

from lunaris_grounding.authorities.authority import SourceAuthority


class ISourceAuthorityStore(Protocol):
    """The editable source-authority config (P6.2): the spine + field packs + denylist (plan §4a).

    Read by the credibility scorer (cached per run) to set a domain's trust prior, and managed via
    the Trusted-sources UI. Server-only, like the corpus — the Supabase impl reads/writes with the
    service-role client; tests run against an in-memory impl. A row's identity is its ``(domain,
    field)`` pair (the table's unique key), so ``upsert`` adds-or-replaces and ``delete`` removes by
    that key — the management surface (T4) needs no separate id.
    """

    async def list_all(self) -> list[SourceAuthority]: ...

    async def upsert(self, authority: SourceAuthority) -> None: ...

    async def delete(self, domain: str, field: SubjectField | None) -> bool: ...
