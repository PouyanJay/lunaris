from collections.abc import Iterable

from lunaris_grounding.authorities.authority import SourceAuthority


class InMemorySourceAuthorityStore:
    """An in-process source-authority config — the deterministic test/no-key backbone.

    Implements the same contract as the Supabase store from a fixed list of authorities, so the
    scorer's tier-prior lookup (and later the trust floor) can be proven offline without a database.
    Used as the no-key fallback seeded with the §4a″ defaults in code; the durable, editable config
    requires Supabase.
    """

    def __init__(self, authorities: Iterable[SourceAuthority] = ()) -> None:
        self._authorities = list(authorities)

    async def list_all(self) -> list[SourceAuthority]:
        return list(self._authorities)
