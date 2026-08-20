from .schema import LearnerModel


class MemoryKnowledgeStore:
    """In-process learner-model store — offline dev and the suite.

    A singleton in the composition root: what a session establishes has to be there for the next
    one, and a per-request store would forget between turns, let alone between sessions.
    """

    def __init__(self) -> None:
        # (owner, graph) -> beliefs. Keyed by both because node ids are graph-local, so one
        # learner's models for two maps are unrelated records that must not merge.
        self._models: dict[tuple[str | None, str], LearnerModel] = {}

    def save(self, model: LearnerModel, *, owner_id: str | None = None) -> None:
        self._models[(owner_id, model.graph_id)] = model

    def load(self, graph_id: str, *, owner_id: str | None = None) -> LearnerModel:
        # Absent is empty, not an error — a first session is the common case. The key includes the
        # owner, so an unscoped read simply misses an owned model rather than reaching it.
        return self._models.get((owner_id, graph_id)) or LearnerModel(graph_id=graph_id)

    def forget(self, graph_id: str, *, owner_id: str | None = None) -> None:
        # Keyed by both, so this reaches exactly one learner's record of one map and no other.
        self._models.pop((owner_id, graph_id), None)
