"""What a knowledge store owes its callers (Phase 2a, T2).

The learner model is the one thing in a session that outlives it (R3, plan §11): a second session on
the same map has to open knowing what the first one established, or every session starts the learner
from nothing and "spaced retrieval" can never span more than one sitting.

Same owner-scoping bar as the session store, and for a sharper reason: this is a record of what
somebody does and does not understand.
"""

from lunaris_live.session import EvidenceKind, LearnerModel, MemoryKnowledgeStore, apply_evidence


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
