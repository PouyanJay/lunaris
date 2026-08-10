"""Live-database proof of the ``live_graphs`` RLS posture (Lunaris Live, Phase 1).

``test_live_graphs_api.py`` proves the app belt — the store scopes by owner, so another owner's
graph is 404. This suite executes the actual policies on a real Postgres with the migrations
applied: owner-only visibility, no write grant for a user at all (compiling and extending go through
the API, which owns the assembly invariants a raw insert would bypass), and no anon reach.

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


def _insert_graph(cur: "psycopg.Cursor", owner: str, graph_id: str) -> None:
    """Write a graph the way the compiler does — service_role, bypassing RLS."""
    payload = {
        "graphId": graph_id,
        "topic": "How neural networks learn",
        "version": 1,
        "nodes": [],
        "topoOrder": [],
        "isAcyclic": True,
    }
    cur.execute(
        """
        insert into public.live_graphs (id, user_id, topic, version, payload)
        values (%s, %s, %s, 1, %s)
        """,
        (graph_id, owner, "How neural networks learn", json.dumps(payload)),
    )


def test_a_learner_sees_only_their_own_graphs(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — two learners, one graph each.
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    my_graph, their_graph = uuid.uuid4().hex, uuid.uuid4().hex
    _seed_user(db, mine)
    _seed_user(db, theirs)
    _insert_graph(db, mine, my_graph)
    _insert_graph(db, theirs, their_graph)

    # Act — become the first learner, the way PostgREST does.
    as_user(db, mine)
    db.execute("select id from public.live_graphs")

    # Assert — the other learner's map is invisible, not merely unreadable.
    assert [row[0] for row in db.fetchall()] == [my_graph]


def test_a_learner_cannot_write_a_graph_directly(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """No INSERT grant: a graph may only be created by the API, which assembles it first.

    A hand-written row could claim ``isAcyclic`` on a graph containing a cycle — exactly the
    self-certification the assembly step exists to prevent.
    """
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_graph(db, owner, uuid.uuid4().hex)


def test_a_learner_cannot_edit_a_graph(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — a graph that really belongs to this learner, so only the grant can refuse.
    owner = str(uuid.uuid4())
    graph_id = uuid.uuid4().hex
    _seed_user(db, owner)
    _insert_graph(db, owner, graph_id)
    as_user(db, owner)

    # Act / Assert — version is the head's monotonic counter; only the server may move it.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("update public.live_graphs set version = 99 where id = %s", (graph_id,))


def test_a_learner_cannot_delete_a_graph(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """Deleting is a server operation too — a graph's assets are purged alongside it."""
    # Arrange
    owner = str(uuid.uuid4())
    graph_id = uuid.uuid4().hex
    _seed_user(db, owner)
    _insert_graph(db, owner, graph_id)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("delete from public.live_graphs where id = %s", (graph_id,))


def test_anon_reaches_nothing(db: "psycopg.Cursor") -> None:
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _insert_graph(db, owner, uuid.uuid4().hex)

    # Act — the unauthenticated PostgREST role.
    db.execute("set local role anon")

    # Assert — anon has no grant at all, so this is a privilege error, not an empty result.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("select id from public.live_graphs")


def test_truncate_is_not_reachable_by_a_user(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """TRUNCATE is a privilege RLS cannot police, so the revoke has to have caught it."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("truncate public.live_graphs")
