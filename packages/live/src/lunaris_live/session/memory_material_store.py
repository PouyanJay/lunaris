from .schema import LessonParts


class MemoryMaterialStore:
    """In-process material store — offline dev and the suite.

    A singleton in the composition root, like the knowledge store: what a turn prefetches has to be
    there for the next request, and a per-request store would forget between turns.
    """

    def __init__(self) -> None:
        # (owner, graph) -> node -> parts. Keyed by both because node ids are graph-local.
        self._held: dict[tuple[str | None, str], dict[str, LessonParts]] = {}

    def save(
        self, graph_id: str, node_id: str, parts: LessonParts, *, owner_id: str | None = None
    ) -> None:
        self._held.setdefault((owner_id, graph_id), {})[node_id] = parts

    def load(self, graph_id: str, *, owner_id: str | None = None) -> dict[str, LessonParts]:
        return dict(self._held.get((owner_id, graph_id), {}))

    def forget(self, graph_id: str, node_id: str, *, owner_id: str | None = None) -> None:
        self._held.get((owner_id, graph_id), {}).pop(node_id, None)
