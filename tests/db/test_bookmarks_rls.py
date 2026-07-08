"""Live-database proof of the bookmarks RLS posture (Unified UI Phase 10).

``test_bookmarks_api.py`` proves the app belt (per-user scoping through the store) against the
in-memory double; this suite executes the actual policies on a real Postgres with the migrations
applied — owner-only visibility and writes, spoofed-owner rejection, the revoked anon grants, the
no-TRUNCATE hardening, and the natural-key toggle semantics. Same harness and gating as the
sibling suites: eval-marked, ``SUPABASE_DB_URL``-gated, one rolled-back transaction per test.
"""

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


def _insert_bookmark(cur: "psycopg.Cursor", owner: str, target_id: str = "m-1-l0") -> None:
    cur.execute(
        """
        insert into public.bookmarks (user_id, kind, course_id, target_id, title)
        values (%s, 'lesson', 'course-1', %s, 'Lesson 1 · Fundamentals')
        """,
        (owner, target_id),
    )


def test_bookmarks_are_visible_to_their_owner_only(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — one save per owner, written the service way (superuser).
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    for user in (user_a, user_b):
        _seed_user(db, user)
        _insert_bookmark(db, user)

    # Act — become user A the way PostgREST does.
    as_user(db, user_a)

    # Assert
    db.execute("select user_id from public.bookmarks")
    owners = {str(row[0]) for row in db.fetchall()}
    assert owners == {user_a}, "bookmarks leaked rows across owners"


def test_spoofed_owner_saves_are_rejected(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    for user in (user_a, user_b):
        _seed_user(db, user)

    # Act / Assert — the WITH CHECK clause rejects a save stamped with someone else's user_id.
    as_user(db, user_a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_bookmark(db, user_b)


def test_cross_owner_removal_is_a_no_op(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — B owns a save.
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    for user in (user_a, user_b):
        _seed_user(db, user)
    _insert_bookmark(db, user_b)

    # Act — A tries to delete B's row by its natural key.
    as_user(db, user_a)
    db.execute(
        "delete from public.bookmarks where kind='lesson' and course_id='course-1'"
        " and target_id='m-1-l0'"
    )
    deleted = db.rowcount

    # Assert — RLS filters the row out of A's DELETE entirely.
    assert deleted == 0


def test_cross_owner_update_is_a_no_op(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — B owns a save.
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    for user in (user_a, user_b):
        _seed_user(db, user)
    _insert_bookmark(db, user_b)

    # Act — A tries to rewrite B's row.
    as_user(db, user_a)
    db.execute("update public.bookmarks set title = 'rewritten' where course_id = 'course-1'")
    updated = db.rowcount

    # Assert — RLS filters the row out of A's UPDATE; B's title stands (checked the service way).
    assert updated == 0
    db.execute("reset role")
    db.execute("select title from public.bookmarks where user_id = %s", (user_b,))
    assert db.fetchone()[0] == "Lesson 1 · Fundamentals"


def test_bookmarks_are_closed_to_anon(db: "psycopg.Cursor") -> None:
    # Act / Assert — closure is a privilege error, not merely an empty result.
    db.execute("set local role anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("select count(*) from public.bookmarks")


def test_no_truncate_grant_for_authenticated(db: "psycopg.Cursor") -> None:
    # TRUNCATE is not governed by RLS — the grant layer is the only defense (the P9 hardening,
    # applied to this table from day one).
    db.execute(
        """
        select privilege_type from information_schema.role_table_grants
        where grantee = 'authenticated' and table_name = 'bookmarks'
          and privilege_type in ('TRUNCATE', 'REFERENCES', 'TRIGGER')
        """
    )
    assert db.fetchall() == []


def test_resaving_upserts_on_the_natural_key(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange
    user = str(uuid.uuid4())
    _seed_user(db, user)

    # Act — the owner saves the same thing twice, the PostgREST way (upsert on conflict).
    as_user(db, user)
    for title in ("First save", "Refreshed save"):
        db.execute(
            """
            insert into public.bookmarks (user_id, kind, course_id, target_id, title)
            values (%s, 'lesson', 'course-1', 'm-1-l0', %s)
            on conflict (user_id, kind, course_id, target_id)
            do update set title = excluded.title, saved_at = now()
            """,
            (user, title),
        )

    # Assert — one row, carrying the refreshed display fields.
    db.execute("select count(*), max(title) from public.bookmarks where user_id = %s", (user,))
    count, title = db.fetchone()
    assert count == 1
    assert title == "Refreshed save"
