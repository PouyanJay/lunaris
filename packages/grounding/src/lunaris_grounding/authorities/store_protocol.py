from typing import Protocol

from lunaris_grounding.authorities.authority import SourceAuthority


class ISourceAuthorityStore(Protocol):
    """The editable source-authority config (P6.2): the spine + field packs + denylist (plan §4a).

    Read by the credibility scorer (cached per run) to set a domain's trust prior, and managed via
    the Trusted-sources UI. Server-only, like the corpus — the Supabase impl reads/writes with the
    service-role client; tests run against an in-memory impl. ``list_all`` returns every row; the
    scorer indexes them by domain. CRUD (add/update/delete) lands with the management surface (T4).
    """

    async def list_all(self) -> list[SourceAuthority]: ...
