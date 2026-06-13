"""Live-database proof of the RLS posture — the DB-level belt behind the app-layer scoping.

``test_user_isolation_api.py`` proves the app belt (service-role writes stamp ``user_id``, reads
filter by it) against in-memory doubles; nothing there executes the actual policies. This suite
connects to a real Postgres with the migrations applied and proves the policies themselves, so a
migration that drops RLS, adds a permissive policy, or forgets a revoke fails a test instead of
shipping.

Gated like the other live suites: ``eval``-marked and skipped without ``SUPABASE_DB_URL``. Against
the local stack (``supabase start`` or ``supabase db start``):

    SUPABASE_DB_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
        uv run pytest tests/db -m eval

Each test runs inside one transaction that is rolled back, so the suite never dirties the database
(harness shared with the other tests/db suites via ``conftest.py``). User context is simulated the
way PostgREST builds it: ``set local role authenticated`` plus the ``request.jwt.claims`` GUC that
``auth.uid()`` reads.
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

_USER_A = str(uuid.uuid4())
_USER_B = str(uuid.uuid4())

_AsUser = Callable[["psycopg.Cursor", str], None]


def _insert_course(cur: "psycopg.Cursor", course_id: str, owner: str | None) -> None:
    cur.execute(
        """
        insert into public.courses (id, payload, status, user_id)
        values (%s, '{}'::jsonb, 'review', %s)
        """,
        (course_id, owner),
    )


def test_every_public_table_has_rls_enabled(db: "psycopg.Cursor") -> None:
    # Act — sweep the catalog, no allowlist: the BLOCKING rule is "every table, no exceptions".
    db.execute(
        """
        select c.relname
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
        """
    )

    # Assert
    assert db.fetchall() == [], "tables without RLS found"


def test_authenticated_user_sees_only_their_own_courses(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange — two owners' courses, written the way the backend writes (service path, owner
    # stamped explicitly).
    a_course, b_course = uuid.uuid4().hex, uuid.uuid4().hex
    _insert_course(db, a_course, _USER_A)
    _insert_course(db, b_course, _USER_B)

    # Act — read as A.
    as_user(db, _USER_A)
    db.execute("select id from public.courses where id in (%s, %s)", (a_course, b_course))

    # Assert — the policy hides B's row; this is the DB belt, not app code.
    assert [row[0] for row in db.fetchall()] == [a_course]


def test_authenticated_user_cannot_update_or_delete_anothers_course(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange
    b_course = uuid.uuid4().hex
    _insert_course(db, b_course, _USER_B)

    # Act — A attacks B's row.
    as_user(db, _USER_A)
    db.execute("update public.courses set status = 'failed' where id = %s", (b_course,))
    updated = db.rowcount
    db.execute("delete from public.courses where id = %s", (b_course,))
    deleted = db.rowcount

    # Assert — both writes hit zero rows.
    assert (updated, deleted) == (0, 0)


def test_authenticated_user_cannot_insert_a_course_for_someone_else(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Act / Assert — the WITH CHECK clause rejects a spoofed owner (and a null owner).
    as_user(db, _USER_A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insert_course(db, uuid.uuid4().hex, _USER_B)


def test_run_events_are_owner_scoped(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — one replay event per owner.
    a_run, b_run = uuid.uuid4().hex, uuid.uuid4().hex
    db.execute(
        """
        insert into public.run_events (run_id, course_id, seq, kind, payload, user_id)
        values (%s, 'c-a', 0, 'progress', '{}'::jsonb, %s),
               (%s, 'c-b', 0, 'progress', '{}'::jsonb, %s)
        """,
        (a_run, _USER_A, b_run, _USER_B),
    )

    # Act — A reads both runs' transcripts.
    as_user(db, _USER_A)
    db.execute("select run_id from public.run_events where run_id in (%s, %s)", (a_run, b_run))

    # Assert — only A's own build transcript is visible.
    assert [row[0] for row in db.fetchall()] == [a_run]


def test_secrets_table_is_force_rls_with_no_policies(db: "psycopg.Cursor") -> None:
    # Act — the posture that makes provider_credentials unreadable by any user-JWT client.
    db.execute(
        """
        select c.relrowsecurity, c.relforcerowsecurity,
               (select count(*) from pg_policies p
                where p.schemaname = 'public' and p.tablename = 'provider_credentials')
        from pg_class c
        where c.oid = 'public.provider_credentials'::regclass
        """
    )
    rls_enabled, rls_forced, policy_count = db.fetchone()

    # Assert — RLS on, FORCED (even the table owner can't bypass), zero policies (nobody qualifies).
    assert (rls_enabled, rls_forced, policy_count) == (True, True, 0)


def test_corpus_tables_are_invisible_to_user_roles(db: "psycopg.Cursor") -> None:
    # The grounding corpus + trust config are server-only: RLS enabled with NO policies, so an
    # authenticated user's direct PostgREST query returns nothing (reads go through the backend).
    for table in ("grounding_documents", "source_authorities"):
        db.execute(
            "select count(*) from pg_policies where schemaname = 'public' and tablename = %s",
            (table,),
        )
        assert db.fetchone()[0] == 0, f"{table} grew a policy — server-only posture broken"


def test_no_public_function_is_executable_by_anon(db: "psycopg.Cursor") -> None:
    # Act — sweep every PROJECT function in public; the BLOCKING rule revokes EXECUTE from anon on
    # each. Extension-owned functions (pgvector ships ~118 operator helpers into public) are
    # excluded — they're the extension's internals, not migration-created surface.
    db.execute(
        """
        select p.oid::regprocedure::text
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and has_function_privilege('anon', p.oid, 'execute')
          and not exists (
              select 1 from pg_depend d
              where d.objid = p.oid and d.classid = 'pg_proc'::regclass and d.deptype = 'e'
          )
        """
    )

    # Assert
    assert db.fetchall() == [], "anon can execute project-defined public functions"


def test_match_rpc_is_not_executable_by_authenticated(db: "psycopg.Cursor") -> None:
    # Act — every overload of the corpus-search RPC (the 3-arg original may coexist with the
    # 4-arg replacement; both must stay server-only).
    db.execute(
        """
        select p.oid::regprocedure::text,
               has_function_privilege('authenticated', p.oid, 'execute')
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public' and p.proname = 'match_grounding_documents'
        """
    )
    rows = db.fetchall()

    # Assert — the RPC exists and no overload is callable with a user JWT.
    assert rows, "match_grounding_documents not found — did the corpus migration apply?"
    assert all(not executable for _, executable in rows), rows
