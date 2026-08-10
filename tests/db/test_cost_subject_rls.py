"""Live-database proof of the cost ledger's rollup key and its access posture (D2).

The in-memory stores prove the *contract* — a course and a graph sharing an id are two subjects.
This suite proves the **database** agrees: the composite key is what Postgres actually enforces, the
backfill left no row unkeyed, and the money stays owner-read / server-write.

That posture matters more here than almost anywhere else in the schema: these are immutable
financial rows, and a user who could write one could invent spend against somebody else's account.

Same harness and gating as the sibling suites: eval-marked, ``SUPABASE_DB_URL``-gated, one
rolled-back transaction per test.
"""

import json
import os
import uuid
from collections.abc import Callable

import pytest
from lunaris_runtime.persistence.legacy_cost_key import legacy_course_id
from lunaris_runtime.schema import CostSubjectType

psycopg = pytest.importorskip("psycopg")

_DB_URL = os.environ.get("SUPABASE_DB_URL", "")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not _DB_URL, reason="SUPABASE_DB_URL not set (needs a live database)"),
]

_AsUser = Callable[["psycopg.Cursor", str], None]


def _seed_user(cur: "psycopg.Cursor", user_id: str) -> None:
    cur.execute("insert into auth.users (id) values (%s) on conflict do nothing", (user_id,))


def _insert_event(
    cur: "psycopg.Cursor",
    owner: str,
    *,
    subject_type: str,
    subject_id: str,
    run_id: str,
    seq: int = 0,
    amount: float = 0.5,
) -> None:
    """Record one ledger row the way the build does — service_role, bypassing RLS.

    ``course_id`` carries the transitional value the store writes (``legacy_course_id``), not the
    bare subject id: the column is still NOT NULL and the rollup's primary key is still on it, so a
    non-course subject has to be namespaced or it collides with a course of the same id.
    """
    cur.execute(
        """
        insert into public.cost_events
            (user_id, run_id, course_id, subject_type, subject_id, seq, component, provider,
             pocket, usage, amount, currency, price_book_version)
        values (%s, %s, %s, %s, %s, %s, 'compile', 'anthropic', 'user_key', %s, %s, 'USD', 'v1')
        """,
        (
            owner,
            run_id,
            legacy_course_id(CostSubjectType(subject_type), subject_id),
            subject_type,
            subject_id,
            seq,
            json.dumps({}),
            amount,
        ),
    )


def _insert_rollup(
    cur: "psycopg.Cursor", owner: str, *, subject_type: str, subject_id: str, total: float
) -> None:
    cur.execute(
        """
        insert into public.course_costs
            (course_id, user_id, subject_type, subject_id, total_amount, currency,
             breakdown, price_book_version)
        values (%s, %s, %s, %s, %s, 'USD', %s, 'v1')
        """,
        (
            legacy_course_id(CostSubjectType(subject_type), subject_id),
            owner,
            subject_type,
            subject_id,
            total,
            json.dumps({}),
        ),
    )


def test_a_course_and_a_graph_that_share_an_id_are_two_rollups(db: "psycopg.Cursor") -> None:
    """The composite key, enforced by Postgres rather than by the app.

    Course ids and graph ids come from independent sequences, so a collision is possible; under the
    old single-column primary key the second product's rollup would have *replaced* the first's.
    """
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    shared = uuid.uuid4().hex

    # Act
    _insert_rollup(db, owner, subject_type="course", subject_id=shared, total=1.0)
    _insert_rollup(db, owner, subject_type="live_graph", subject_id=shared, total=3.0)

    # Assert — two rows, each holding its own total.
    db.execute(
        "select subject_type, total_amount from public.course_costs where subject_id = %s"
        " order by subject_type",
        (shared,),
    )
    assert db.fetchall() == [("course", 1.0), ("live_graph", 3.0)]


def test_one_subject_cannot_have_two_rollups(db: "psycopg.Cursor") -> None:
    """The upsert's conflict target has to be unique or a recompute appends instead of replacing —
    which would show a learner two different totals for the same thing."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    graph = uuid.uuid4().hex
    _insert_rollup(db, owner, subject_type="live_graph", subject_id=graph, total=1.0)

    # Act / Assert
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_rollup(db, owner, subject_type="live_graph", subject_id=graph, total=2.0)


def test_the_backfill_keys_a_row_written_the_old_way(db: "psycopg.Cursor") -> None:
    """The migration's backfill, re-run against a row shaped the way the previous release writes.

    Every row that predates this migration carries a ``course_id`` and no subject, and a row left
    unkeyed simply vanishes from the drill-through — which reads by subject. Asserted by seeding a
    legacy-shaped row and running the migration's own statement over it, rather than by counting
    unkeyed rows table-wide: a table-wide count passes or fails on whatever else happens to be in
    the database, which makes it a test of the environment rather than of the backfill.
    """
    # Arrange — a course's spend, recorded before this migration existed.
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    legacy_id = uuid.uuid4().hex
    db.execute(
        """
        insert into public.cost_events
            (user_id, run_id, course_id, subject_id, seq, component, provider, pocket,
             usage, amount, currency, price_book_version)
        values (%s, 'r-legacy', %s, null, 0, 'planner', 'anthropic', 'platform', %s, 1.0,
                'USD', 'v1')
        """,
        (owner, legacy_id, json.dumps({})),
    )

    # Act — the statement the migration runs.
    db.execute("update public.cost_events set subject_id = course_id where subject_id is null")

    # Assert — keyed, and keyed as a course (the default the column was added with).
    db.execute(
        "select subject_type, subject_id from public.cost_events where course_id = %s", (legacy_id,)
    )
    assert db.fetchall() == [("course", legacy_id)]


def test_a_learner_sees_only_their_own_costs(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — two learners, one metered graph each.
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    _seed_user(db, mine)
    _seed_user(db, theirs)
    my_graph, their_graph = uuid.uuid4().hex, uuid.uuid4().hex
    _insert_event(db, mine, subject_type="live_graph", subject_id=my_graph, run_id="r-mine")
    _insert_event(db, theirs, subject_type="live_graph", subject_id=their_graph, run_id="r-theirs")

    # Act
    as_user(db, mine)
    db.execute("select subject_id from public.cost_events")

    # Assert — another learner's spend is invisible, not merely unreadable.
    assert [row[0] for row in db.fetchall()] == [my_graph]


def test_a_learner_cannot_invent_spend(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """No INSERT grant on the ledger. Costs are recorded by the build via service_role; a user who
    could write here could attribute spend to another account, in rows nobody may correct."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    as_user(db, owner)

    # Act / Assert
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_event(
            db, owner, subject_type="live_graph", subject_id=uuid.uuid4().hex, run_id="r-forged"
        )


def test_a_learner_cannot_erase_their_own_spend(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    """An append-only ledger is only append-only if DELETE is ungranted too — otherwise a tenant
    can make their own usage disappear."""
    # Arrange
    owner = str(uuid.uuid4())
    _seed_user(db, owner)
    graph = uuid.uuid4().hex
    _insert_event(db, owner, subject_type="live_graph", subject_id=graph, run_id="r-mine")

    # Act / Assert — refused by the missing grant...
    as_user(db, owner)
    db.execute("savepoint attempted_delete")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("delete from public.cost_events where subject_id = %s", (graph,))
    # Released to a savepoint, not rolled back: a bare rollback would discard the Arrange too, and
    # the row would then be "gone" for a reason that has nothing to do with the policy.
    db.execute("rollback to savepoint attempted_delete")

    # ...and the row survived. Asserted separately because the two layers fail differently: a
    # missing GRANT raises, while RLS's default-deny silently filters a delete to zero rows without
    # erroring at all. A test that only caught the exception would call a regression "protected"
    # the moment somebody granted DELETE without adding a policy.
    db.execute("select count(*) from public.cost_events where subject_id = %s", (graph,))
    assert db.fetchone()[0] == 1
