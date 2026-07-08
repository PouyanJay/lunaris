"""Live-database proof of the learning-telemetry RLS posture (Unified UI Phase 9).

``test_activity_api.py`` proves the app belt (per-user scoping through the store) against the
in-memory double; this suite executes the actual policies on a real Postgres with the migrations
applied — owner-only visibility, spoofed-owner rejection, the revoked anon grants, and the
append-only posture on ``learning_events`` (no UPDATE/DELETE for authenticated, and no TRUNCATE
anywhere — the privilege RLS cannot police). Same harness and gating as the sibling suites:
eval-marked, ``SUPABASE_DB_URL``-gated, one rolled-back transaction per test.
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

_ACTIVITY_TABLES = ("learning_events", "study_minutes")


def _seed_user(cur: "psycopg.Cursor", user_id: str) -> None:
    # Both tables FK auth.users (on delete cascade), so give each actor a real user row.
    cur.execute("insert into auth.users (id) values (%s) on conflict do nothing", (user_id,))


def _insert_event(cur: "psycopg.Cursor", owner: str, course_id: str) -> None:
    cur.execute(
        """
        insert into public.learning_events (user_id, event_type, course_id, course_title)
        values (%s, 'completed', %s, 'How HTTPS works')
        """,
        (owner, course_id),
    )


def _insert_minute(cur: "psycopg.Cursor", owner: str) -> None:
    cur.execute(
        """
        insert into public.study_minutes (user_id, bucket_start)
        values (%s, date_trunc('minute', now()))
        on conflict do nothing
        """,
        (owner,),
    )


def test_activity_is_visible_to_its_owner_only(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — one row per owner in each table, written the service way (superuser).
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    course = uuid.uuid4().hex
    for user in (user_a, user_b):
        _seed_user(db, user)
        _insert_event(db, user, course)
        _insert_minute(db, user)

    # Act — become user A the way PostgREST does.
    as_user(db, user_a)

    # Assert — each table shows exactly user A's own row.
    for table in _ACTIVITY_TABLES:
        db.execute(f"select user_id from public.{table}")
        owners = {str(row[0]) for row in db.fetchall()}
        assert owners == {user_a}, f"{table} leaked rows across owners"


def test_spoofed_owner_writes_are_rejected(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    for user in (user_a, user_b):
        _seed_user(db, user)

    # Act / Assert — the WITH CHECK clause rejects telemetry stamped with someone else's
    # user_id, symmetrically on both tables.
    as_user(db, user_a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_event(db, user_b, uuid.uuid4().hex)
    db.connection.rollback()
    for user in (user_a, user_b):
        _seed_user(db, user)
    as_user(db, user_a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_minute(db, user_b)


def test_activity_tables_are_closed_to_anon(db: "psycopg.Cursor") -> None:
    # Act — the anon role has no grants at all on either table.
    db.execute("set local role anon")

    # Assert — closure is a privilege error, not merely an empty result.
    for table in _ACTIVITY_TABLES:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute(f"select count(*) from public.{table}")
        db.connection.rollback()
        db.execute("set local role anon")


def test_learning_events_are_append_only_for_users(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — an owned event, written the service way.
    user = str(uuid.uuid4())
    _seed_user(db, user)
    _insert_event(db, user, uuid.uuid4().hex)

    # Act / Assert — even the OWNER cannot rewrite or erase history from a user JWT: no UPDATE or
    # DELETE grant exists on learning_events for authenticated.
    as_user(db, user)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("update public.learning_events set course_title = 'rewritten'")
    db.connection.rollback()
    _seed_user(db, user)
    as_user(db, user)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("delete from public.learning_events")


def test_no_truncate_grant_for_authenticated(db: "psycopg.Cursor") -> None:
    # TRUNCATE is not governed by RLS at all — the only defense is the grant layer. This pins the
    # security-review fix (including the backfill onto the Phase-2 progress tables).
    db.execute(
        """
        select table_name, privilege_type
        from information_schema.role_table_grants
        where grantee = 'authenticated'
          and table_name in ('learning_events', 'study_minutes',
                             'objective_progress', 'lesson_progress', 'learner_course_state')
          and privilege_type in ('TRUNCATE', 'REFERENCES', 'TRIGGER')
        """
    )
    assert db.fetchall() == []


def test_minute_buckets_must_be_minute_aligned(db: "psycopg.Cursor") -> None:
    # Arrange
    user = str(uuid.uuid4())
    _seed_user(db, user)

    # Act / Assert — a mid-minute timestamp violates the bucket check (no bucket gaming).
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(
            "insert into public.study_minutes (user_id, bucket_start)"
            " values (%s, date_trunc('minute', now()) + interval '30 seconds')",
            (user,),
        )
