"""Live-database proof of the ``live_materials`` RLS posture (Lunaris Live, Phase 2c, T4).

The prefetched first-turn material of a concept, one row per (learner, map, concept). Owner-read /
server-write like its siblings: a learner writing their own material could not corrupt a belief
(material never grades anything) but would put words in the tutor's mouth, so the write path is
the server's. The identity index treats a NULL owner as one owner, so an unowned upsert lands on
one row.

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

_PARTS = {"workedExample": {"title": "Worked", "steps": ["one"]}, "hint": "h", "practice": ["p"]}


def _seed_user(cur: "psycopg.Cursor", user_id: str) -> None:
    cur.execute("insert into auth.users (id) values (%s) on conflict do nothing", (user_id,))


def _keep(
    cur: "psycopg.Cursor", owner: str | None, graph_id: str = "g1", node_id: str = "b"
) -> None:
    """Write material the way the prefetcher does — service_role, bypassing RLS."""
    cur.execute(
        """
        insert into public.live_materials (user_id, graph_id, node_id, payload)
        values (%s, %s, %s, %s)
        """,
        (owner, graph_id, node_id, json.dumps(_PARTS)),
    )


def test_a_learner_sees_only_their_own_material(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_user(db, mine)
    _seed_user(db, theirs)
    _keep(db, mine, node_id="mine")
    _keep(db, theirs, node_id="theirs")

    as_user(db, mine)
    db.execute("select node_id from public.live_materials")

    assert [row[0] for row in db.fetchall()] == ["mine"]


def test_a_learner_cannot_write_material(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    as_user(db, owner)

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _keep(db, owner)


@pytest.mark.parametrize(
    "statement",
    [
        "update public.live_materials set payload = '{}' where user_id = %s",
        "delete from public.live_materials where user_id = %s",
    ],
)
def test_a_learner_cannot_edit_or_delete_material(
    db: "psycopg.Cursor", as_user: _AsUser, statement: str
) -> None:
    """One refusal per test: a refused statement aborts the transaction, and a second one in the
    same block would fail for that reason rather than for the grant."""
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _keep(db, owner)
    as_user(db, owner)

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(statement, (owner,))


def test_anon_reaches_nothing(db: "psycopg.Cursor") -> None:
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _keep(db, owner)

    db.execute("set local role anon")

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("select node_id from public.live_materials")


def test_one_row_per_learner_map_and_concept_and_an_unowned_row_is_one_owner(
    db: "psycopg.Cursor",
) -> None:
    """The identity: a second write for the same (owner, map, concept) is a conflict, not a second
    row — including for the unowned scope, where NULL would otherwise never equal NULL and every
    upsert would insert again."""
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    _keep(db, owner)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _keep(db, owner)


def test_an_unowned_row_is_one_owner(db: "psycopg.Cursor") -> None:
    _keep(db, None)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _keep(db, None)


def test_an_unowned_row_is_nobodys(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """The nullable owner's whole justification: a NULL owner is ONE owner (the auth-off path), and
    it is not "everybody's" — no authenticated learner can read it, because ``auth.uid()`` is never
    NULL for a real token and NULL never equals anything."""
    someone = str(uuid.uuid4())
    _seed_user(db, someone)
    _keep(db, None, node_id="unowned")

    as_user(db, someone)
    db.execute("select node_id from public.live_materials")

    assert db.fetchall() == []
