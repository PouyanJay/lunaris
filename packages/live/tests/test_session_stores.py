"""What a session store owes its callers, whichever one is wired (Phase 2a, T1).

The API suite runs with auth unconfigured, so ``owner_id`` is ``None`` everywhere in it — which
means it structurally *cannot* exercise cross-owner isolation. This is where that boundary is
proved, at the store, on its own terms.

A session is the most personal row in the product: a transcript of somebody being taught, including
everything they got wrong. The store is the last thing between one learner's and another's, because
the loop writes through the service-role client, which bypasses RLS.
"""

import pytest
from lunaris_live.session import (
    DirectorMove,
    MemorySessionStore,
    MoveKind,
    Session,
    SessionTurn,
)


def _session(session_id: str = "s1") -> Session:
    return Session(
        session_id=session_id,
        graph_id="g1",
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="a", reason="Opening concept."),
                tutor="Let's start with A.",
            )
        ],
    )


def test_a_session_round_trips_for_its_owner() -> None:
    # Arrange
    store = MemorySessionStore()
    store.save(_session(), owner_id="learner-1")

    # Act
    loaded = store.load("s1", owner_id="learner-1")

    # Assert — the turns survive, not just the id: the transcript IS the session.
    assert loaded.turns[0].move.kind is MoveKind.INTRODUCE
    assert loaded.turns[0].tutor == "Let's start with A."


def test_another_learners_session_is_not_found() -> None:
    """Not-found rather than forbidden: a session's existence is owner-scoped information, and
    "that session exists but isn't yours" already tells a stranger something."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session(), owner_id="learner-1")

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        store.load("s1", owner_id="learner-2")


def test_an_owned_session_is_not_served_to_an_unscoped_read() -> None:
    """A caller with no owner must not inherit access to an owned session.

    Unreachable through the API today — ``optional_user_id`` 401s anonymous callers whenever auth is
    configured, so ``owner_id=None`` only happens on the auth-off single-user path. That is a
    property of two config flags agreeing, not an invariant of this store, so the store refuses on
    its own terms rather than trusting the wiring above it to stay that way. Phase 1's graph store
    settled this exact question; a session holds more about a person than a graph does.
    """
    # Arrange
    store = MemorySessionStore()
    store.save(_session(), owner_id="learner-1")

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        store.load("s1", owner_id=None)


def test_an_unscoped_session_round_trips_in_the_auth_off_path() -> None:
    # Arrange — no owner anywhere: offline dev, where there is exactly one user.
    store = MemorySessionStore()
    store.save(_session(), owner_id=None)

    # Act / Assert
    assert store.load("s1", owner_id=None).session_id == "s1"


def test_an_unscoped_session_is_not_served_to_an_owner() -> None:
    """The other direction of the same rule. Without it, one learner signing in would inherit every
    session left behind by the single-user path."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session(), owner_id=None)

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        store.load("s1", owner_id="learner-1")


def test_a_session_that_was_never_saved_is_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        MemorySessionStore().load("nope", owner_id="learner-1")


def test_saving_the_same_session_again_replaces_its_head() -> None:
    """Every turn rewrites the row, so the store has to be an upsert on the id rather than an
    append — a second save that created a second session would fork the transcript."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session(), owner_id="learner-1")
    grown = _session().model_copy(
        update={
            "turns": [
                *_session().turns,
                SessionTurn(
                    seq=2,
                    move=DirectorMove(kind=MoveKind.RETRIEVE, node_id="a", reason="Coming back."),
                    tutor="What happens when it doubles?",
                ),
            ]
        }
    )

    # Act
    store.save(grown, owner_id="learner-1")

    # Assert
    assert [turn.seq for turn in store.load("s1", owner_id="learner-1").turns] == [1, 2]
