"""Live-database proof of the ``live_sessions`` RLS posture (Lunaris Live, Phase 2a).

``test_live_sessions_api.py`` proves the app belt — the store scopes by owner, so another learner's
session is 404. This suite executes the actual policies on a real Postgres with the migrations
applied: owner-only visibility, no write grant for a learner at all (every turn goes through the
API, which owns the loop's invariants), and no anon reach.

A session is the most personal row in the product — it is a transcript of somebody being taught,
including everything they got wrong — so the posture matters more here than it did for a graph, and
is proved rather than assumed.

Same harness and gating as the sibling suites: eval-marked, ``SUPABASE_DB_URL``-gated, one
rolled-back transaction per test.
"""

import json
import os
import uuid
from collections.abc import Callable

import pytest

psycopg = pytest.importorskip("psycopg")

_DB_URL = os.environ.get("SUPABASE_DB_URL", "")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not _DB_URL, reason="SUPABASE_DB_URL not set (needs a live database)"),
]

_AsUser = Callable[["psycopg.Cursor", str], None]


def _seed_user(cur: "psycopg.Cursor", user_id: str) -> None:
    cur.execute("insert into auth.users (id) values (%s) on conflict do nothing", (user_id,))


def _insert_session(cur: "psycopg.Cursor", owner: str, session_id: str) -> None:
    """Write a session the way the loop does — service_role, bypassing RLS."""
    payload = {
        "sessionId": session_id,
        "graphId": "g1",
        "status": "active",
        "turns": [
            {
                "seq": 1,
                "move": {"kind": "introduce", "nodeId": "a", "reason": "Opening concept."},
                "tutor": "Let's start with A.",
            }
        ],
    }
    cur.execute(
        """
        insert into public.live_sessions (id, user_id, graph_id, status, turn_count, payload)
        values (%s, %s, %s, 'active', 1, %s)
        """,
        (session_id, owner, "g1", json.dumps(payload)),
    )


def test_a_learner_sees_only_their_own_sessions(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — two learners, one session each.
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    my_session, their_session = uuid.uuid4().hex, uuid.uuid4().hex
    _seed_user(db, mine)
    _seed_user(db, theirs)
    _insert_session(db, mine, my_session)
    _insert_session(db, theirs, their_session)

    # Act — become the first learner, the way PostgREST does.
    as_user(db, mine)
    db.execute("select id from public.live_sessions")

    # Assert — the other learner's transcript is invisible, not merely unreadable.
    assert [row[0] for row in db.fetchall()] == [my_session]


def test_a_learner_cannot_write_a_session_directly(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """No INSERT grant. A hand-written session could claim turns that never happened — and the
    learner model is built from exactly those turns, so it would be a way to fabricate mastery."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_session(db, owner, uuid.uuid4().hex)


def test_a_learner_cannot_edit_their_own_session(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — a session that really belongs to this learner, so only the grant can refuse.
    owner = str(uuid.uuid4())
    session_id = uuid.uuid4().hex
    _seed_user(db, owner)
    _insert_session(db, owner, session_id)
    as_user(db, owner)

    # Act / Assert — editing the transcript is editing the evidence the director reasons from.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("update public.live_sessions set status = 'closed' where id = %s", (session_id,))


def test_a_learner_cannot_delete_a_session(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """Deleting is a server operation: a session's purge has to take its cost rows with it."""
    # Arrange
    owner = str(uuid.uuid4())
    session_id = uuid.uuid4().hex
    _seed_user(db, owner)
    _insert_session(db, owner, session_id)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("delete from public.live_sessions where id = %s", (session_id,))


def test_anon_reaches_nothing(db: "psycopg.Cursor") -> None:
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _insert_session(db, owner, uuid.uuid4().hex)

    # Act — the unauthenticated PostgREST role.
    db.execute("set local role anon")

    # Assert — anon has no grant at all, so this is a privilege error, not an empty result.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("select id from public.live_sessions")


def test_truncate_is_not_reachable_by_a_user(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """TRUNCATE is a privilege RLS cannot police, so the revoke has to have caught it."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("truncate public.live_sessions")


def test_a_session_status_is_constrained_to_the_two_it_can_be(db: "psycopg.Cursor") -> None:
    """``SessionStatus`` is a closed set in Python; the column has to agree, or a bad write reaches
    the surface as a status the web has no branch for."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)

    # Act / Assert — service_role bypasses RLS but not a check constraint.
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            """
            insert into public.live_sessions (id, user_id, graph_id, status, payload)
            values (%s, %s, 'g1', 'abandoned', '{}'::jsonb)
            """,
            (uuid.uuid4().hex, owner),
        )


def test_a_placing_session_is_a_status_the_table_accepts(db: "psycopg.Cursor") -> None:
    """P2c T1: a session now opens *placing* — on a map that has not been compiled yet — and the
    row's status CHECK has to admit it, or the first topic-opened session in production fails at
    the write with a constraint error nothing upstream can translate. Expand-only: the two
    statuses that existed keep their meaning."""
    # Arrange
    owner = str(uuid.uuid4())
    session_id = uuid.uuid4().hex
    _seed_user(db, owner)

    # Act — written as the loop writes it (the service role, or here the local superuser: both
    # bypass RLS, neither bypasses a CHECK): a placing session, one interview turn.
    payload = {
        "sessionId": session_id,
        "graphId": "g-pending",
        "topic": "Bayes' theorem",
        "status": "placing",
        "turns": [
            {
                "seq": 1,
                "move": {"kind": "place", "nodeId": None, "reason": "Nothing to teach from yet."},
                "tutor": "What have you already met of Bayes' theorem?",
            }
        ],
    }
    db.execute(
        """
        insert into public.live_sessions (id, user_id, graph_id, status, turn_count, payload)
        values (%s, %s, %s, 'placing', 1, %s)
        """,
        (session_id, owner, "g-pending", json.dumps(payload)),
    )

    # Assert — it is there, as written.
    db.execute("select status from public.live_sessions where id = %s", (session_id,))
    assert db.fetchone() == ("placing",)


def test_an_unknown_status_is_still_refused(db: "psycopg.Cursor") -> None:
    """Widening the CHECK for ``placing`` must not have turned it into "anything goes"."""
    owner = str(uuid.uuid4())
    _seed_user(db, owner)

    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            """
            insert into public.live_sessions (id, user_id, graph_id, status, turn_count, payload)
            values (%s, %s, 'g1', 'paused', 1, '{}')
            """,
            (uuid.uuid4().hex, owner),
        )
