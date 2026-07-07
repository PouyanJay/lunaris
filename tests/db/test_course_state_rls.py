"""Live-database proof of the learner_course_state RLS posture (Unified UI Phase 3).

``test_progress_api.py`` proves the app belt (per-user scoping through the store) against the
in-memory double; this suite executes the actual policies on a real Postgres with the migration
applied — owner-only visibility, spoofed-owner rejection, upsert-preserves-position semantics,
and the revoked anon grants. Same harness and gating as the sibling suites: eval-marked,
``SUPABASE_DB_URL``-gated, one rolled-back transaction per test.
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
    # The table FKs auth.users (on delete cascade), so give each actor a real user row.
    cur.execute("insert into auth.users (id) values (%s) on conflict do nothing", (user_id,))


def _insert_state(
    cur: "psycopg.Cursor", owner: str, course_id: str, last_lesson_id: str | None = None
) -> None:
    cur.execute(
        """
        insert into public.learner_course_state (user_id, course_id, last_lesson_id)
        values (%s, %s, %s)
        """,
        (owner, course_id, last_lesson_id),
    )


def test_course_state_is_visible_to_its_owner_only(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — one state row per owner, written the service way (superuser).
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    course = uuid.uuid4().hex
    for user in (user_a, user_b):
        _seed_user(db, user)
        _insert_state(db, user, course)

    # Act / Assert — A sees exactly their own row.
    as_user(db, user_a)
    db.execute("select user_id from public.learner_course_state where course_id = %s", (course,))
    assert [row[0] for row in db.fetchall()] == [uuid.UUID(user_a)]


def test_course_state_writes_cannot_touch_anothers_rows(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange — B owns a state row.
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    course = uuid.uuid4().hex
    for user in (user_a, user_b):
        _seed_user(db, user)
    _insert_state(db, user_b, course, "m-1-l0")

    # Act — A attacks B's row.
    as_user(db, user_a)
    db.execute(
        "update public.learner_course_state set last_lesson_id = 'hijack' where course_id = %s",
        (course,),
    )
    updated = db.rowcount
    db.execute("delete from public.learner_course_state where course_id = %s", (course,))
    deleted = db.rowcount

    # Assert — both writes hit zero rows.
    assert (updated, deleted) == (0, 0)


def test_course_state_insert_rejects_a_spoofed_owner(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    for user in (user_a, user_b):
        _seed_user(db, user)

    # Act / Assert — the WITH CHECK clause rejects rows stamped with someone else's user_id.
    as_user(db, user_a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_state(db, user_b, uuid.uuid4().hex)


def test_course_state_is_closed_to_anon(db: "psycopg.Cursor") -> None:
    # Act / Assert — the revoked grants mean anon can't even attempt a read (permission denied,
    # not merely zero rows).
    db.execute("set local role anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("select count(*) from public.learner_course_state")


def test_course_state_writes_are_closed_to_anon(db: "psycopg.Cursor") -> None:
    # Act / Assert — the revoked grants deny every write posture too, symmetric with the P2
    # tables' proof. Each statement re-enters anon because the rollback drops the role switch.
    statements = (
        "insert into public.learner_course_state (user_id, course_id) "
        "values (gen_random_uuid(), 'c-1')",
        "update public.learner_course_state set last_lesson_id = 'x'",
        "delete from public.learner_course_state",
    )
    for statement in statements:
        db.execute("set local role anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute(statement)
        db.connection.rollback()


def test_owner_cannot_reassign_a_row_to_another_user(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange — A owns a state row; B exists.
    user_a, user_b = str(uuid.uuid4()), str(uuid.uuid4())
    course = uuid.uuid4().hex
    for user in (user_a, user_b):
        _seed_user(db, user)
    _insert_state(db, user_a, course)

    # Act / Assert — the UPDATE policy's WITH CHECK rejects flipping user_id to someone else
    # (an ownership hijack would otherwise move the row outside A's own visibility).
    as_user(db, user_a)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(
            "update public.learner_course_state set user_id = %s where course_id = %s",
            (user_b, course),
        )


def test_upsert_without_position_preserves_it(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # The API's bare-touch contract, proven at the SQL layer: an ON CONFLICT update that omits
    # last_lesson_id leaves the recorded position intact while advancing last_opened_at.
    user_a = str(uuid.uuid4())
    course = uuid.uuid4().hex
    _seed_user(db, user_a)

    as_user(db, user_a)
    _insert_state(db, user_a, course, "m-1-l0")
    db.execute(
        """
        insert into public.learner_course_state (user_id, course_id, last_opened_at)
        values (%s, %s, now() + interval '1 second')
        on conflict (user_id, course_id)
        do update set last_opened_at = excluded.last_opened_at
        """,
        (user_a, course),
    )
    db.execute(
        "select last_lesson_id from public.learner_course_state where course_id = %s", (course,)
    )
    assert db.fetchone()[0] == "m-1-l0"


def test_owner_can_write_their_own_row_directly(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # The allowed path, exercised as the user (not the service role): grants + policies must let
    # an owner insert, update, and delete their own state row.
    user_a = str(uuid.uuid4())
    course = uuid.uuid4().hex
    _seed_user(db, user_a)

    as_user(db, user_a)
    _insert_state(db, user_a, course)
    db.execute(
        "update public.learner_course_state set last_lesson_id = 'm-1-l0' where course_id = %s",
        (course,),
    )
    assert db.rowcount == 1
    db.execute("delete from public.learner_course_state where course_id = %s", (course,))
    assert db.rowcount == 1
