"""Live-database proof of the learner-progress RLS posture (Unified UI Phase 2).

``test_progress_api.py`` proves the app belt (per-user scoping through the store) against the
in-memory double; this suite executes the actual policies on a real Postgres with the migrations
applied — owner-only visibility, spoofed-owner rejection, and the revoked anon grants. Same
harness and gating as the sibling suites: eval-marked, ``SUPABASE_DB_URL``-gated, one rolled-back
transaction per test.
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

_PROGRESS_TABLES = ("objective_progress", "lesson_progress")


def _seed_user(cur: "psycopg.Cursor", user_id: str) -> None:
    # The progress tables FK auth.users (on delete cascade), so give each actor a real user row.
    cur.execute("insert into auth.users (id) values (%s) on conflict do nothing", (user_id,))


def _insert_objective(cur: "psycopg.Cursor", owner: str, course_id: str, index: int = 0) -> None:
    cur.execute(
        """
        insert into public.objective_progress (user_id, course_id, module_id, objective_index)
        values (%s, %s, 'm-1', %s)
        """,
        (owner, course_id, index),
    )


def _insert_lesson(cur: "psycopg.Cursor", owner: str, course_id: str) -> None:
    cur.execute(
        """
        insert into public.lesson_progress (user_id, course_id, lesson_id, state)
        values (%s, %s, 'm-1-l0', 'in_progress')
        """,
        (owner, course_id),
    )


def test_progress_is_visible_to_its_owner_only(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — one mark per owner in each table, written the service way (superuser).
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    course = uuid.uuid4().hex
    for user in (user_a, user_b):
        _seed_user(db, user)
        _insert_objective(db, user, course)
        _insert_lesson(db, user, course)

    # Act / Assert — A sees exactly their own rows in both tables.
    as_user(db, user_a)
    for table in _PROGRESS_TABLES:
        db.execute(f"select user_id from public.{table} where course_id = %s", (course,))
        assert [row[0] for row in db.fetchall()] == [uuid.UUID(user_a)], table


def test_progress_writes_cannot_touch_anothers_rows(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — B owns a mark in each table.
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    course = uuid.uuid4().hex
    for user in (user_a, user_b):
        _seed_user(db, user)
    _insert_objective(db, user_b, course)
    _insert_lesson(db, user_b, course)

    # Act — A attacks B's rows.
    as_user(db, user_a)
    db.execute("update public.lesson_progress set state = 'done' where course_id = %s", (course,))
    updated = db.rowcount
    db.execute("delete from public.objective_progress where course_id = %s", (course,))
    deleted = db.rowcount

    # Assert — both writes hit zero rows.
    assert (updated, deleted) == (0, 0)


def test_progress_insert_rejects_a_spoofed_owner(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    for user in (user_a, user_b):
        _seed_user(db, user)

    # Act / Assert — the WITH CHECK clause rejects rows stamped with someone else's user_id,
    # symmetrically on both tables.
    as_user(db, user_a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_objective(db, user_b, uuid.uuid4().hex)
    db.connection.rollback()
    as_user(db, user_a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_lesson(db, user_b, uuid.uuid4().hex)


def test_progress_tables_are_closed_to_anon(db: "psycopg.Cursor") -> None:
    # Act / Assert — the revoked grants mean anon can't even attempt a read (permission denied,
    # not merely zero rows).
    db.execute("set local role anon")
    for table in _PROGRESS_TABLES:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute(f"select count(*) from public.{table}")
        db.connection.rollback()
        # A rollback drops the role switch with the rest of the transaction state; re-enter anon
        # so the second table is probed under the same posture.
        db.execute("set local role anon")


def test_owner_can_write_their_own_rows_directly(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # The allowed path, exercised as the user (not the service role): the grants + policies must
    # let an owner insert, update, and delete their own marks.
    user_a = str(uuid.uuid4())
    course = uuid.uuid4().hex
    _seed_user(db, user_a)

    as_user(db, user_a)
    _insert_objective(db, user_a, course)
    _insert_lesson(db, user_a, course)
    db.execute("update public.lesson_progress set state = 'done' where course_id = %s", (course,))
    assert db.rowcount == 1
    db.execute("delete from public.objective_progress where course_id = %s", (course,))
    assert db.rowcount == 1


def test_owner_cannot_reassign_a_row_to_another_user(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange — A owns a lesson mark; B exists.
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    course = uuid.uuid4().hex
    for user in (user_a, user_b):
        _seed_user(db, user)
    _insert_lesson(db, user_a, course)

    # Act / Assert — the UPDATE policy's WITH CHECK rejects handing the row to someone else.
    as_user(db, user_a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(
            "update public.lesson_progress set user_id = %s where course_id = %s",
            (user_b, course),
        )


def test_progress_writes_are_closed_to_anon(db: "psycopg.Cursor") -> None:
    # The blanket revoke denies anon every operation, not just reads.
    statements = (
        "insert into public.objective_progress (user_id, course_id, module_id, objective_index)"
        " values (gen_random_uuid(), 'c', 'm', 0)",
        "update public.lesson_progress set state = 'done'",
        "delete from public.objective_progress",
    )
    for statement in statements:
        db.execute("set local role anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute(statement)
        db.connection.rollback()
