"""Live-database proof of the video-jobs posture — the job spine's DB belt.

The `video_jobs` table is the queue the explainer-video worker drains (plan: V0-T0). Its posture:
owner-scoped SELECT for `authenticated` (the UI may read its own jobs), **server-only writes**
(enqueue/claim/complete go through the API or worker via service_role — a user JWT can never
insert, update, or claim a job, not even its own). The `course-videos` bucket is private; objects
are readable by their owner only, keyed on the first path segment of the
`{user_id}/{course_id}/{job_id}/…` convention, and writable by nobody but service_role.

Same harness as ``test_rls_policies.py`` (shared fixtures in ``conftest.py``): eval-marked,
``SUPABASE_DB_URL``-gated, one rolled-back transaction per test. The catalog sweep there
(`test_every_public_table_has_rls_enabled`) covers this table's RLS bit automatically.
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


def _provision_user(cur: "psycopg.Cursor", user_id: str) -> None:
    """Create the auth.users row the video_jobs owner FK requires (rolled back with the test)."""
    cur.execute("insert into auth.users (id) values (%s) on conflict (id) do nothing", (user_id,))


def _insert_job(cur: "psycopg.Cursor", job_id: str, owner: str) -> None:
    """Write a job the way the backend writes it: service path, owner stamped explicitly."""
    _provision_user(cur, owner)
    cur.execute(
        """
        insert into public.video_jobs (id, user_id, course_id, lesson_id, kind, input_hash)
        values (%s, %s, 'course-1', 'lesson-1', 'lesson', 'hash-1')
        """,
        (job_id, owner),
    )


def test_authenticated_user_sees_only_their_own_jobs(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange — one job per owner, written via the service path.
    a_job, b_job = uuid.uuid4().hex, uuid.uuid4().hex
    _insert_job(db, a_job, _USER_A)
    _insert_job(db, b_job, _USER_B)

    # Act — read as A.
    as_user(db, _USER_A)
    db.execute("select id from public.video_jobs where id in (%s, %s)", (a_job, b_job))

    # Assert — the policy hides B's job.
    assert [row[0] for row in db.fetchall()] == [a_job]


def test_authenticated_user_cannot_insert_jobs_at_all(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange — A exists as a real auth user.
    _provision_user(db, _USER_A)

    # Act / Assert — even the OWNER's JWT cannot enqueue; writes are server-only (enqueue must
    # pass the API, which enforces the VIDEO_GENERATION_ENABLED flag and the keyed-tier check).
    as_user(db, _USER_A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(
            """
            insert into public.video_jobs (id, user_id, course_id, lesson_id, kind, input_hash)
            values (%s, %s, 'course-1', 'lesson-1', 'lesson', 'hash-1')
            """,
            (uuid.uuid4().hex, _USER_A),
        )


def test_authenticated_user_cannot_claim_their_own_job(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange
    a_job = uuid.uuid4().hex
    _insert_job(db, a_job, _USER_A)

    # Act / Assert — UPDATE (a claim / status flip) is denied outright: no grant, no policy.
    as_user(db, _USER_A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("update public.video_jobs set status = 'ready' where id = %s", (a_job,))


def test_authenticated_user_cannot_delete_their_own_job(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Arrange
    a_job = uuid.uuid4().hex
    _insert_job(db, a_job, _USER_A)

    # Act / Assert — DELETE is denied the same way; the queue's history is server-owned.
    as_user(db, _USER_A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("delete from public.video_jobs where id = %s", (a_job,))


def test_anon_cannot_read_video_jobs(db: "psycopg.Cursor") -> None:
    # Arrange
    _insert_job(db, uuid.uuid4().hex, _USER_A)

    # Act / Assert — the revoke strips anon entirely; not even an empty result, a hard denial.
    db.execute("set local role anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("select id from public.video_jobs")


def test_account_deletion_cascades_jobs(db: "psycopg.Cursor") -> None:
    # Arrange
    a_job = uuid.uuid4().hex
    _insert_job(db, a_job, _USER_A)

    # Act — the service path deletes the auth user (account deletion).
    db.execute("delete from auth.users where id = %s", (_USER_A,))

    # Assert — the FK cascade reaps the job; no orphaned rows survive the owner.
    db.execute("select count(*) from public.video_jobs where id = %s", (a_job,))
    assert db.fetchone()[0] == 0


def test_course_videos_bucket_is_private(db: "psycopg.Cursor") -> None:
    # Act
    db.execute("select public from storage.buckets where id = 'course-videos'")
    row = db.fetchone()

    # Assert — the bucket exists and is NOT public; playback goes through signed URLs.
    assert row is not None, "course-videos bucket missing — did the V0-T0 migration apply?"
    assert row[0] is False


def test_storage_objects_are_owner_prefix_scoped(db: "psycopg.Cursor", as_user: _AsUser) -> None:
    # Arrange — one object per owner under the {user_id}/{course_id}/{job_id}/ convention,
    # written the way the worker writes (service path; `owner` stays NULL — the policy is
    # path-based by design, so it must hold with no owner column to lean on).
    a_obj = f"{_USER_A}/course-1/job-a/final.mp4"
    b_obj = f"{_USER_B}/course-1/job-b/final.mp4"
    db.execute(
        "insert into storage.objects (bucket_id, name) "
        "values ('course-videos', %s), ('course-videos', %s)",
        (a_obj, b_obj),
    )

    # Act — A lists the bucket.
    as_user(db, _USER_A)
    db.execute("select name from storage.objects where bucket_id = 'course-videos'")

    # Assert — only A's own path prefix is visible.
    assert [row[0] for row in db.fetchall()] == [a_obj]


def test_authenticated_cannot_write_course_videos_objects(
    db: "psycopg.Cursor", as_user: _AsUser
) -> None:
    # Act / Assert — no INSERT policy exists for the bucket, so even an owner-prefixed write
    # from a user JWT is rejected; only service_role (the worker) puts objects here.
    as_user(db, _USER_A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(
            "insert into storage.objects (bucket_id, name) values ('course-videos', %s)",
            (f"{_USER_A}/course-1/job-x/final.mp4",),
        )
