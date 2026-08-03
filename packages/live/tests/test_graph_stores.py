"""The store contract both backends must honour.

Owner scoping is the property that keeps one learner's maps out of another's session, and the API
suite cannot exercise it: `optional_user_id` yields ``None`` for every request while auth is
unconfigured, which is how the whole test suite runs. So the mismatch case is proven here, against
the in-memory store that offline dev and CI actually use, rather than being left entirely to the
`SUPABASE_DB_URL`-gated RLS suite that most runs skip.
"""

import pytest
from lunaris_live.graph import ConceptGraph, ConceptNode, MemoryGraphStore


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
