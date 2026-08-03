from typing import Protocol

from ..schema import ConceptGraph


class IGraphStore(Protocol):
    """Where a compiled concept graph is persisted and re-read.

    Mirrors Studio's ``ICourseStore`` contract so the two products' persistence behaves alike:
    ``load`` raises ``FileNotFoundError`` when no graph has that id (the store-agnostic not-found
    signal the API turns into a 404), and ``owner_id`` scopes every operation — ``save`` stamps it,
    ``load`` constrains to it, so another owner's graph is *not found* rather than forbidden.

    One deliberate divergence from ``ICourseStore``: ``owner_id=None`` means *unowned*, not
    *unscoped*. It matches only graphs saved without an owner (the auth-off single-user path) and
    never reaches an owned one. Studio's looser reading is safe only because anonymous callers are
    401'd wherever auth is configured — which is an agreement between two config flags rather than a
    guarantee this store makes, and Live's graphs are mutable, so the blast radius is larger.

    Synchronous, because supabase-py is; async callers off-load via ``asyncio.to_thread``.
    """

    def save(self, graph: ConceptGraph, *, owner_id: str | None = None) -> None: ...

    def load(self, graph_id: str, *, owner_id: str | None = None) -> ConceptGraph: ...
