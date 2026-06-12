"""Live-database proof of the atomic claim — FOR UPDATE SKIP LOCKED does what the queue promises.

The in-memory double's concurrency test (packages/runtime) proves the *semantics*; this suite
proves the *mechanism* on real Postgres: two workers claiming concurrently can never get the same
job, because the row lock (not app code) arbitrates. Uses two real connections with overlapping
uncommitted transactions — the strongest honest simulation of two worker processes.

Setup rows must be visible across connections, so this suite COMMITS its fixtures and cleans up
in ``finally`` (deleting the auth user cascades the jobs away via the owner FK).

Isolation caveat: ``claim_video_job`` takes the GLOBALLY oldest queued row — these tests assume
no parallel pytest workers against the same database and no leftover queued rows from an aborted
prior run (a stale row would be claimed instead of this run's fixtures and fail the assertions).
The local stack is single-runner, so this holds; if it ever flakes, sweep stale ``video_jobs``
rows first.
"""

import os
import uuid
from collections.abc import Iterator

import pytest

psycopg = pytest.importorskip("psycopg")

_DB_URL = os.environ.get("SUPABASE_DB_URL", "")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not _DB_URL, reason="SUPABASE_DB_URL not set (needs a live database)"),
]


def test_claim_function_is_not_executable_by_user_roles(db: "psycopg.Cursor") -> None:
    # Act — the claim is the worker's (service_role) alone.
    db.execute(
        """
        select has_function_privilege('anon', p.oid, 'execute'),
               has_function_privilege('authenticated', p.oid, 'execute')
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = 'claim_video_job'
        """
    )
    rows = db.fetchall()

    # Assert — the function exists and neither user role may call it.
    assert rows, "claim_video_job not found — did the V0-T1 migration apply?"
    assert all(row == (False, False) for row in rows), rows


@pytest.fixture
def committed_jobs() -> Iterator[tuple[str, str]]:
    """Two committed queued jobs (oldest first), reaped afterwards via the owner-FK cascade."""
    owner = str(uuid.uuid4())
    old_job, new_job = uuid.uuid4().hex, uuid.uuid4().hex
    setup = psycopg.connect(_DB_URL, autocommit=True)
    try:
        setup.execute("insert into auth.users (id) values (%s)", (owner,))
        setup.execute(
            """
            insert into public.video_jobs
                (id, user_id, course_id, lesson_id, kind, input_hash, created_at)
            values
                (%s, %s, 'course-1', 'lesson-1', 'lesson', 'h', now() - interval '2 minutes'),
                (%s, %s, 'course-1', 'lesson-2', 'lesson', 'h', now() - interval '1 minute')
            """,
            (old_job, owner, new_job, owner),
        )
        yield old_job, new_job
    finally:
        setup.execute("delete from auth.users where id = %s", (owner,))
        setup.close()


def test_concurrent_claimers_never_get_the_same_job(committed_jobs: tuple[str, str]) -> None:
    # Arrange — the fixture committed two queued jobs (oldest first).
    old_job, new_job = committed_jobs

    # Act — two workers' transactions overlap: A claims and has NOT committed when B claims.
    with psycopg.connect(_DB_URL) as conn_a, psycopg.connect(_DB_URL) as conn_b:
        conn_a.autocommit = False
        conn_b.autocommit = False
        try:
            a_claim = conn_a.execute("select id from public.claim_video_job('worker-a')")
            a_row = a_claim.fetchone()

            b_claim = conn_b.execute("select id from public.claim_video_job('worker-b')")
            b_row = b_claim.fetchone()

            b_again = conn_b.execute("select id from public.claim_video_job('worker-b')")
            b_empty = b_again.fetchone()

            # Assert — A holds the oldest job's lock, so B skips it and takes the next; with
            # both locked, a third claim finds nothing. The lock arbitrates, not app code.
            assert a_row is not None and a_row[0] == old_job
            assert b_row is not None and b_row[0] == new_job
            assert b_empty is None
        finally:
            conn_a.rollback()
            conn_b.rollback()


def test_claim_stamps_the_lease(committed_jobs: tuple[str, str]) -> None:
    # Arrange — the fixture committed two queued jobs; the oldest is the claim target.
    old_job, _ = committed_jobs

    # Act
    with psycopg.connect(_DB_URL) as conn:
        conn.autocommit = False
        try:
            row = conn.execute(
                """
                select id, status, claimed_by, attempts, claimed_at is not null
                from public.claim_video_job('worker-a')
                """
            ).fetchone()

            # Assert — one call atomically flips the status and stamps the whole lease.
            assert row == (old_job, "planning", "worker-a", 1, True)
        finally:
            conn.rollback()
