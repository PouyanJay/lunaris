"""What a knowledge store owes its callers (Phase 2a, T2).

The learner model is the one thing in a session that outlives it (R3, plan §11): a second session on
the same map has to open knowing what the first one established, or every session starts the learner
from nothing and "spaced retrieval" can never span more than one sitting.

Same owner-scoping bar as the session store, and for a sharper reason: this is a record of what
somebody does and does not understand.
"""

from lunaris_live.session import (
    EvidenceKind,
    LearnerModel,
    MemoryKnowledgeStore,
    SupabaseKnowledgeStore,
    apply_evidence,
)


def _model() -> LearnerModel:
    return apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.MET, at_turn=1)


def test_what_one_session_established_is_there_for_the_next() -> None:
    """The whole point of persisting it."""
    # Arrange
    store = MemoryKnowledgeStore()
    store.save(_model(), owner_id="learner-1")

    # Act
    loaded = store.load("g1", owner_id="learner-1")

    # Assert — the belief AND what it rests on survive; a belief without its evidence count is a
    # number nobody can audit.
    assert loaded.nodes["a"].estimate == _model().nodes["a"].estimate
    assert loaded.nodes["a"].evidence_count == 1


def test_a_learner_with_no_history_on_a_map_starts_empty_rather_than_missing() -> None:
    """A first session is the common case, not an error. Raising here would make every caller
    write the same try/except, and one of them would eventually get it wrong."""
    # Act
    model = MemoryKnowledgeStore().load("g1", owner_id="learner-1")

    # Assert
    assert model.graph_id == "g1"
    assert model.nodes == {}


def test_another_learners_knowledge_is_never_returned() -> None:
    """Not merely private — returning it would have the director skip concepts *this* learner has
    never seen, on the strength of somebody else's answers."""
    # Arrange
    store = MemoryKnowledgeStore()
    store.save(_model(), owner_id="learner-1")

    # Act / Assert — empty, not an error: as far as learner-2 is concerned they have no history.
    assert store.load("g1", owner_id="learner-2").nodes == {}


def test_an_owned_model_is_not_served_to_an_unscoped_read() -> None:
    """Same rule the session and graph stores hold: ``owner_id=None`` means *unowned*, never
    *unscoped*. A store must not depend on the auth wiring above it staying configured."""
    # Arrange
    store = MemoryKnowledgeStore()
    store.save(_model(), owner_id="learner-1")

    # Act / Assert
    assert store.load("g1", owner_id=None).nodes == {}


def test_knowledge_is_scoped_to_the_map_it_was_learned_on() -> None:
    """Node ids are graph-local, so mastery of "a" on one map says nothing about "a" on another."""
    # Arrange
    store = MemoryKnowledgeStore()
    store.save(_model(), owner_id="learner-1")

    # Act / Assert
    assert store.load("g2", owner_id="learner-1").nodes == {}


def test_saving_again_replaces_the_belief_rather_than_appending_to_it() -> None:
    """The model is a head, not a log. The evidence count inside it is the history."""
    # Arrange
    store = MemoryKnowledgeStore()
    store.save(_model(), owner_id="learner-1")
    grown = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=2)

    # Act
    store.save(grown, owner_id="learner-1")

    # Assert
    assert store.load("g1", owner_id="learner-1").nodes["a"].evidence_count == 2


# ── forgetting a topic (T5) ────────────────────────────────────────────────────────────────────


def test_forgetting_a_topic_clears_only_that_learner() -> None:
    """The reset verb's safety property, and the one the API suite structurally cannot prove: it
    runs with auth unconfigured, so ``owner_id`` is ``None`` in every test in it. Unscoped, "forget
    this topic" would clear every learner's progress on it, with no way to get it back."""
    # Arrange
    store = MemoryKnowledgeStore()
    store.save(_model(), owner_id="learner-1")
    store.save(_model(), owner_id="learner-2")

    # Act
    store.forget("g1", owner_id="learner-1")

    # Assert
    assert store.load("g1", owner_id="learner-1").nodes == {}
    assert store.load("g1", owner_id="learner-2").nodes != {}


def test_forgetting_a_topic_clears_only_that_map() -> None:
    """Node ids are graph-local, so two maps are unrelated records. A reset that reached past its
    own map would take away progress the learner never asked about."""
    # Arrange
    store = MemoryKnowledgeStore()
    store.save(_model(), owner_id="learner-1")
    store.save(
        apply_evidence(LearnerModel(graph_id="g2"), "a", EvidenceKind.MET, at_turn=1),
        owner_id="learner-1",
    )

    # Act
    store.forget("g1", owner_id="learner-1")

    # Assert
    assert store.load("g2", owner_id="learner-1").nodes != {}


def test_an_unscoped_reset_cannot_reach_an_owned_record() -> None:
    """The mirror of ``test_an_owned_model_is_not_served_to_an_unscoped_read``: unscoped means
    *unowned*, never *everyone*, on the way out as much as on the way in."""
    # Arrange
    store = MemoryKnowledgeStore()
    store.save(_model(), owner_id="learner-1")

    # Act
    store.forget("g1")

    # Assert
    assert store.load("g1", owner_id="learner-1").nodes != {}


def test_forgetting_a_topic_with_nothing_to_forget_is_quiet() -> None:
    """Idempotent by contract: a learner pressing it twice must not meet an error the second time,
    and the first press on a topic never taught is the same non-event."""
    # Arrange
    store = MemoryKnowledgeStore()

    # Act / Assert: no exception is the assertion.
    store.forget("never-taught", owner_id="learner-1")


# ── the durable store, where the predicate actually lives ──────────────────────────────────────


class RecordingSupabase:
    """A fake that FILTERS, so the store's own predicates decide the answer.

    The review's one important finding was that every owner-scoping mutation in this journey ran
    against the memory twin — a dict lookup — while production is a query-builder chain where a
    dropped ``.eq()`` would be caught by nothing. `SupabaseKnowledgeStore.forget` had no coverage of
    any kind. This is still a fake and not Postgres; what it proves is that the store asks the right
    questions, which is exactly where a mis-keyed predicate lives.
    """

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self._matched: list[dict] = []

    def table(self, _name: str) -> "RecordingSupabase":
        self._matched = list(self.rows)
        return self

    def delete(self) -> "RecordingSupabase":
        return self

    def eq(self, column: str, value: object) -> "RecordingSupabase":
        self._matched = [row for row in self._matched if row.get(column) == value]
        return self

    def is_(self, column: str, value: object) -> "RecordingSupabase":
        self._matched = [row for row in self._matched if row.get(column) is value]
        return self

    def execute(self) -> object:
        for row in self._matched:
            self.rows.remove(row)
        return type("Result", (), {"data": list(self._matched)})()


def _belief(*, owner: str | None, graph: str = "g1") -> dict:
    return {"user_id": owner, "graph_id": graph, "node_id": "a", "estimate": 0.9}


def test_the_durable_store_forgets_only_that_learners_record() -> None:
    """Unscoped, "forget this topic" would clear every learner's progress on it, irrecoverably."""
    # Arrange
    rows = [_belief(owner="learner-1"), _belief(owner="learner-2")]
    store = SupabaseKnowledgeStore(client=RecordingSupabase(rows))

    # Act
    store.forget("g1", owner_id="learner-1")

    # Assert
    assert rows == [_belief(owner="learner-2")]


def test_the_durable_store_forgets_only_that_map() -> None:
    """Node ids are graph-local, so two maps are unrelated records."""
    # Arrange
    rows = [_belief(owner="learner-1"), _belief(owner="learner-1", graph="g2")]
    store = SupabaseKnowledgeStore(client=RecordingSupabase(rows))

    # Act
    store.forget("g1", owner_id="learner-1")

    # Assert
    assert rows == [_belief(owner="learner-1", graph="g2")]


def test_an_unscoped_durable_reset_cannot_reach_an_owned_record() -> None:
    """Unscoped means *unowned*, never *everyone*, on the way out as much as on the way in."""
    # Arrange
    rows = [_belief(owner="learner-1")]
    store = SupabaseKnowledgeStore(client=RecordingSupabase(rows))

    # Act
    store.forget("g1")

    # Assert
    assert rows == [_belief(owner="learner-1")]
