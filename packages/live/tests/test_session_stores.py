"""What a session store owes its callers, whichever one is wired (Phase 2a, T1).

The API suite runs with auth unconfigured, so ``owner_id`` is ``None`` everywhere in it — which
means it structurally *cannot* exercise cross-owner isolation. This is where that boundary is
proved, at the store, on its own terms.

A session is the most personal row in the product: a transcript of somebody being taught, including
everything they got wrong. The store is the last thing between one learner's and another's, because
the loop writes through the service-role client, which bypasses RLS.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from lunaris_live.session import (
    DirectorMove,
    MemorySessionStore,
    MoveKind,
    Session,
    SessionFormatError,
    SessionStatus,
    SessionTurn,
    StaleAnswerError,
    SupabaseSessionStore,
)
from lunaris_runtime.persistence import PersistenceError


def _session(session_id: str = "s1") -> Session:
    return Session(
        session_id=session_id,
        graph_id="g1",
        started_at=datetime(2026, 8, 9, 21, 0, tzinfo=UTC),
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="a", reason="Opening concept."),
                tutor="Let's start with A.",
                run_id="r1",
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
                    run_id="r2",
                ),
            ]
        }
    )

    # Act
    store.save(grown, owner_id="learner-1")

    # Assert
    assert [turn.seq for turn in store.load("s1", owner_id="learner-1").turns] == [1, 2]


def test_a_placing_session_round_trips_with_its_topic() -> None:
    """A placement is a session whose map has not landed yet (P2c T1). Its status and its topic
    have to survive the store: a reload mid-interview knows what the interview is about only from
    the row, because there is no graph to read it off."""
    # Arrange
    store = MemorySessionStore()
    placing = Session(
        session_id="s-placing",
        graph_id="g-pending",
        topic="Bayes' theorem",
        status=SessionStatus.PLACING,
        started_at=datetime(2026, 8, 19, 9, 0, tzinfo=UTC),
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.PLACE, reason="Nothing to teach from yet."),
                tutor="What have you already met of Bayes' theorem?",
                run_id="r1",
            )
        ],
    )
    store.save(placing, owner_id="learner-1")

    # Act
    loaded = store.load("s-placing", owner_id="learner-1")

    # Assert — pinned by value, not merely "round-tripped": a store that dropped the topic or
    # coerced the status to ACTIVE would still return a Session.
    assert loaded.status is SessionStatus.PLACING
    assert loaded.topic == "Bayes' theorem"
    assert loaded.turns[0].move.kind is MoveKind.PLACE


# ── deleting, and listing, are scoped like every other read (T4, T2) ───────────────────────────


def test_a_session_is_deleted_only_by_its_own_owner() -> None:
    """The delete verb's whole safety property. Unscoped, a learner could remove somebody else's
    transcript by guessing an id, and would learn the id existed by watching it succeed."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session("mine"), owner_id="learner-a")

    # Act / Assert: another learner cannot reach it, and neither can an unscoped caller.
    with pytest.raises(FileNotFoundError):
        store.delete("mine", owner_id="learner-b")
    with pytest.raises(FileNotFoundError):
        store.delete("mine")
    # And it is still there afterwards, which is the half a refusal alone would not prove.
    assert store.load("mine", owner_id="learner-a").session_id == "mine"

    # Act: its owner can.
    store.delete("mine", owner_id="learner-a")

    # Assert
    with pytest.raises(FileNotFoundError):
        store.load("mine", owner_id="learner-a")


def test_deleting_a_session_that_was_never_there_is_not_found() -> None:
    """So a caller cannot tell "already gone" from "never existed" by the shape of the answer."""
    # Arrange
    store = MemorySessionStore()

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        store.delete("nope", owner_id="learner-a")


def test_a_learner_lists_only_their_own_sessions() -> None:
    """A list is where a scoping mistake shows somebody else's teaching history all at once rather
    than one row of it, which is why this is proved at the store and not only at the API."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session("mine"), owner_id="learner-a")
    store.save(_session("theirs"), owner_id="learner-b")
    store.save(_session("nobodys"))

    # Act
    listed = store.recent(owner_id="learner-a")

    # Assert
    assert [summary.session_id for summary in listed] == ["mine"]


def test_the_newest_session_is_listed_first() -> None:
    """Ordering is the store's job, so both implementations answer the same way and no surface has
    to re-sort. Two saves inside one clock tick is the case a wall clock alone would get wrong."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session("older"), owner_id="learner-a")
    store.save(_session("newer"), owner_id="learner-a")

    # Act
    listed = store.recent(owner_id="learner-a")

    # Assert
    assert [summary.session_id for summary in listed] == ["newer", "older"]


def test_a_re_saved_session_moves_to_the_front() -> None:
    """ "Newest" means last moved, not first opened: a learner coming back wants the thing they were
    last doing. A turn re-saves the session, so this is what every answer does to the list."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session("first"), owner_id="learner-a")
    store.save(_session("second"), owner_id="learner-a")

    # Act: the older one takes a turn.
    store.save(_session("first"), owner_id="learner-a")

    # Assert
    assert [summary.session_id for summary in store.recent(owner_id="learner-a")] == [
        "first",
        "second",
    ]


def test_an_open_session_is_only_seen_by_its_own_owner() -> None:
    """``has_open_on`` gates a destructive act (T5's reset), so a wrong answer either blocks a
    learner from clearing their own record or lets them clear it out from under a live session."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session("theirs"), owner_id="learner-b")

    # Act / Assert
    assert store.has_open_on("g1", owner_id="learner-b") is True
    assert store.has_open_on("g1", owner_id="learner-a") is False
    assert store.has_open_on("g1") is False


def test_a_finished_session_is_not_an_open_one() -> None:
    """Both terminal statuses, because a learner who *left* a session must be as free to reset the
    topic as one who finished it: the guard exists to stop a live session overwriting the reset, and
    neither of these will ever write again."""
    # Arrange
    store = MemorySessionStore()
    open_one = _session("s1")
    store.save(open_one, owner_id="learner-a")
    assert store.has_open_on("g1", owner_id="learner-a") is True

    # Act / Assert
    for done in (SessionStatus.CLOSED, SessionStatus.ABANDONED):
        store.save(open_one.model_copy(update={"status": done}), owner_id="learner-a")
        assert store.has_open_on("g1", owner_id="learner-a") is False


def test_an_open_session_on_another_map_does_not_count() -> None:
    """The block is per map. One unfinished session must not freeze every other topic's reset."""
    # Arrange
    store = MemorySessionStore()
    store.save(_session("elsewhere").model_copy(update={"graph_id": "g2"}), owner_id="learner-a")

    # Act / Assert
    assert store.has_open_on("g1", owner_id="learner-a") is False


# ── a row this build cannot read ───────────────────────────────────────────────────────────────


class FakeSupabase:
    """The narrow slice of supabase-py the session store uses: a chainable query over one row."""

    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def table(self, _name: str) -> "FakeSupabase":
        return self

    def select(self, *_columns: str) -> "FakeSupabase":
        return self

    def eq(self, _column: str, _value: object) -> "FakeSupabase":
        return self

    def is_(self, _column: str, _value: object) -> "FakeSupabase":
        return self

    def limit(self, _count: int) -> "FakeSupabase":
        return self

    def execute(self) -> Any:
        class Result:
            data = [] if self._row is None else [self._row]

        return Result()


def test_a_session_this_build_cannot_parse_is_not_an_outage() -> None:
    """The failure has to be distinguishable from a backend being down, because the two want
    opposite things from the caller: an outage is worth retrying and a row written by a schema this
    build no longer understands never will be. Undistinguished, it reads as a transient 503 and
    invites a learner to reload forever on a session that cannot come back.

    Live under a rolling deploy: T4 added ``run_id`` to a turn, and T5 and T6 both add more.
    """
    # Arrange — a session saved before turns carried the run that produced them.
    stale = {
        "sessionId": "s1",
        "graphId": "g1",
        "status": "active",
        "startedAt": "2026-08-09T21:00:00Z",
        "turns": [
            {
                "seq": 1,
                "move": {"kind": "introduce", "nodeId": "a", "reason": "Opening concept."},
                "tutor": "Let's start with A.",
            }
        ],
    }
    store = SupabaseSessionStore(client=FakeSupabase({"payload": stale}))

    # Act / Assert
    with pytest.raises(SessionFormatError):
        store.load("s1", owner_id=None)


def test_a_session_nobody_can_date_is_unreadable_rather_than_re_clocked() -> None:
    """``started_at`` is required and has no default, and this is why.

    A default would run afresh on every parse, so a row stored before the field existed would be
    stamped "now" on each read — handing a session one turn from its budget a whole new one, every
    time it was reloaded. That is the unbounded session the budget exists to prevent, arriving
    silently. Unreadable is the honest answer for a session nobody can date.
    """
    # Arrange — a session written before sessions were dated.
    undated = {
        "sessionId": "s1",
        "graphId": "g1",
        "status": "active",
        "turns": [
            {
                "seq": 1,
                "move": {"kind": "introduce", "nodeId": "a", "reason": "Opening concept."},
                "tutor": "Let's start with A.",
                "runId": "r1",
            }
        ],
    }
    store = SupabaseSessionStore(client=FakeSupabase({"payload": undated}))

    # Act / Assert
    with pytest.raises(SessionFormatError):
        store.load("s1", owner_id=None)


def test_a_readable_row_still_loads_through_the_same_path() -> None:
    """The guard above must not be a wall: the ordinary row goes through untouched."""
    # Arrange
    payload = _session().model_dump(mode="json", by_alias=True)
    store = SupabaseSessionStore(client=FakeSupabase({"payload": payload}))

    # Act
    loaded = store.load("s1", owner_id=None)

    # Assert
    assert loaded.turns[0].run_id == "r1"


def test_a_format_failure_is_still_a_persistence_failure_to_anyone_not_looking_for_it() -> None:
    """Callers that only know about ``PersistenceError`` keep working — the distinction is
    available to the router that wants it, not imposed on everything that touches a store."""
    # Arrange
    store = SupabaseSessionStore(client=FakeSupabase({"payload": {"nonsense": True}}))

    # Act / Assert
    with pytest.raises(PersistenceError):
        store.load("s1", owner_id=None)


# ── two answers at once ────────────────────────────────────────────────────────────────────────


def test_a_write_conditioned_on_a_head_that_has_moved_is_refused() -> None:
    """The concurrent double-submit, settled where it can actually be settled.

    Two answers sent at the same moment both read a one-turn session, so both pass every check made
    against the snapshot they hold — the staleness guard in ``take_turn`` sees identical, correct
    values in each request. Only the store knows which one arrived second, and without this it
    silently overwrites the first: a graded answer and the model calls behind it vanish from the
    transcript, with nobody told.
    """
    # Arrange — the first answer has landed, so the stored session is two turns long.
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
                    run_id="r2",
                ),
            ]
        }
    )
    store.save(grown, owner_id="learner-1", expect_turns=1)

    # Act / Assert — the second request still believes the session is one turn long.
    with pytest.raises(StaleAnswerError):
        store.save(grown, owner_id="learner-1", expect_turns=1)

    # And the winner is untouched.
    assert len(store.load("s1", owner_id="learner-1").turns) == 2


def test_creating_a_session_is_the_one_unconditional_write() -> None:
    """``expect_turns=None`` is not a loophole — it is the only moment there is nothing to compare
    against, because the session did not exist a moment ago."""
    # Arrange / Act
    store = MemorySessionStore()
    store.save(_session(), owner_id="learner-1")

    # Assert
    assert store.load("s1", owner_id="learner-1").session_id == "s1"
