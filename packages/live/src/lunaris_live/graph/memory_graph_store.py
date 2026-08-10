from .graph_version_conflict_error import GraphVersionConflictError
from .schema import ConceptGraph


class MemoryGraphStore:
    """An in-process graph store — the offline/dev and test destination.

    Owner scoping is enforced the same way the durable store enforces it: a graph belonging to
    another owner reads back as *not found*, never as forbidden, so tests of the API's 404 behaviour
    exercise the real rule rather than a store that is permissive by accident.
    """

    def __init__(self) -> None:
        self._graphs: dict[str, tuple[str | None, ConceptGraph]] = {}

    def save(
        self,
        graph: ConceptGraph,
        *,
        owner_id: str | None = None,
        expected_version: int | None = None,
    ) -> None:
        if expected_version is not None:
            stored = self._graphs.get(graph.graph_id)
            if stored is None or stored[1].version != expected_version:
                raise GraphVersionConflictError(graph.graph_id)
        self._graphs[graph.graph_id] = (owner_id, graph)

    def load(self, graph_id: str, *, owner_id: str | None = None) -> ConceptGraph:
        found = self._graphs.get(graph_id)
        if found is None:
            raise FileNotFoundError(graph_id)
        stored_owner, graph = found
        # Exact match, so an *unscoped* read cannot reach an owned graph either. Studio's course
        # store treats ``owner_id=None`` as "unscoped, see everything", which is safe there because
        # it only happens on the auth-off single-user path — but that safety is a property of two
        # config flags agreeing, not of the store. Live's store refuses on its own terms instead.
        if stored_owner != owner_id:
            raise FileNotFoundError(graph_id)
        return graph
