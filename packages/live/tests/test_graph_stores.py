"""The store contract both backends must honour.

Owner scoping is the property that keeps one learner's maps out of another's session, and the API
suite cannot exercise it: `optional_user_id` yields ``None`` for every request while auth is
unconfigured, which is how the whole test suite runs. So the mismatch case is proven here, against
the in-memory store that offline dev and CI actually use, rather than being left entirely to the
`SUPABASE_DB_URL`-gated RLS suite that most runs skip.
"""

import pytest
from lunaris_live.graph import (
    ConceptGraph,
    ConceptNode,
    GraphVersionConflictError,
    MemoryGraphStore,
)


def _graph(graph_id: str = "g1") -> ConceptGraph:
    return ConceptGraph(
        graph_id=graph_id,
        topic="How neural networks learn",
        nodes=[ConceptNode(id="a", name="Gradient", definition="…")],
    )


def test_a_graph_is_readable_by_the_owner_who_compiled_it() -> None:
    # Arrange
    store = MemoryGraphStore()
    store.save(_graph(), owner_id="learner-1")

    # Act / Assert
    assert store.load("g1", owner_id="learner-1").graph_id == "g1"


def test_another_owners_graph_is_not_found_rather_than_forbidden() -> None:
    """Not-found, not a refusal: whether a graph exists is itself owner-scoped information, and a
    403 would confirm the id to someone who should not know it."""
    # Arrange
    store = MemoryGraphStore()
    store.save(_graph(), owner_id="learner-1")

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        store.load("g1", owner_id="learner-2")


def test_an_owned_graph_is_not_served_to_an_unscoped_read() -> None:
    """A caller with no owner must not inherit access to an owned graph.

    Today this is unreachable through the API — `optional_user_id` 401s anonymous callers whenever
    auth is configured, so `owner_id=None` only happens in the auth-off single-user path. That is a
    property of two config flags agreeing, not an invariant of this store, so the store refuses on
    its own terms rather than trusting the wiring above it to stay that way.
    """
    # Arrange
    store = MemoryGraphStore()
    store.save(_graph(), owner_id="learner-1")

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        store.load("g1", owner_id=None)


def test_an_unscoped_graph_round_trips_in_the_auth_off_path() -> None:
    # Arrange — no owner anywhere: offline dev, where there is exactly one user.
    store = MemoryGraphStore()
    store.save(_graph(), owner_id=None)

    # Act / Assert
    assert store.load("g1", owner_id=None).graph_id == "g1"


def test_a_missing_graph_raises_the_store_agnostic_not_found_signal() -> None:
    # Act / Assert — FileNotFoundError is the contract the router turns into a 404.
    with pytest.raises(FileNotFoundError):
        MemoryGraphStore().load("never-compiled")


def test_a_cold_compile_writes_without_claiming_a_version() -> None:
    # Arrange / Act — no expected_version: there is nothing to race with on a first write.
    store = MemoryGraphStore()
    store.save(_graph(), owner_id="learner-1")

    # Assert
    assert store.load("g1", owner_id="learner-1").version == 1


def test_an_extension_that_lost_the_race_is_refused_rather_than_overwriting() -> None:
    """Two turns of one session can overlap. Without this the later write silently discards the
    earlier one's concepts, which the learner experiences as a question that never landed."""
    # Arrange — both extensions read version 1.
    store = MemoryGraphStore()
    store.save(_graph(), owner_id="learner-1")
    first = _graph().model_copy(update={"version": 2})
    second = _graph().model_copy(update={"version": 2})

    # Act — the first one home wins.
    store.save(first, owner_id="learner-1", expected_version=1)

    # Assert — the loser is told, not silently applied on top.
    with pytest.raises(GraphVersionConflictError):
        store.save(second, owner_id="learner-1", expected_version=1)
    assert store.load("g1", owner_id="learner-1").version == 2


def test_extending_a_graph_that_is_gone_is_a_conflict_not_a_resurrection() -> None:
    # Arrange — nothing stored; a stale extension arrives for a purged graph.
    store = MemoryGraphStore()

    # Act / Assert — a conditional write must not create the row it was meant to update.
    with pytest.raises(GraphVersionConflictError):
        store.save(_graph(), owner_id="learner-1", expected_version=1)
