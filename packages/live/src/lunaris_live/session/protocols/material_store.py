from typing import Protocol

from ..schema import LessonParts


class IMaterialStore(Protocol):
    """Persistence for a node's first-turn material, prefetched ahead of the learner (P2c T4).

    Keyed by owner, map and concept, like the learner model, and for the same reason: material is
    written for one learner's map (the graph is per learner, C1 grows it per session). ``load``
    answers everything held for one map — a handful of entries at most, one node ahead — and never
    raises for absence: an empty map is the ordinary state, not an error. ``forget`` is how a turn
    that used an entry lets it go, so a second pass over a concept generates fresh.

    ``owner_id`` scopes it, and unscoped means *unowned* rather than *see everything*.
    """

    def save(
        self, graph_id: str, node_id: str, parts: LessonParts, *, owner_id: str | None = None
    ) -> None: ...

    def load(self, graph_id: str, *, owner_id: str | None = None) -> dict[str, LessonParts]: ...

    def forget(self, graph_id: str, node_id: str, *, owner_id: str | None = None) -> None: ...
