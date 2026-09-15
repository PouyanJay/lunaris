"""Real private snapshot persistence and source access/revision lifecycle."""

import os
from uuid import uuid4

import psycopg
import pytest
from lunaris_api.live.corpus.studio_resolver import StudioCorpusResolver
from lunaris_api.live.corpus.unavailable import CorpusUnavailableError
from lunaris_live.corpus.models.snapshot_key import SnapshotKey
from lunaris_live.corpus.schemas.reference import CorpusReference
from lunaris_live.corpus.stores.supabase_snapshot_store import SupabaseCorpusSnapshotStore
from lunaris_runtime.persistence import PersistenceError, SupabaseCourseStore
from lunaris_runtime.schema import Course
from psycopg import sql
from psycopg.types.json import Jsonb
from test_studio_corpus_resolver import course_payload

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY"), reason="local database required"
    ),
]


async def test_private_snapshot_revision_identity_access_revocation_and_deletion() -> None:
    owner, other, course_id = str(uuid4()), str(uuid4()), uuid4().hex
    courses = SupabaseCourseStore(
        url_env="LOCAL_SUPABASE_URL", service_key_env="LOCAL_SUPABASE_SERVICE_KEY"
    )
    snapshots = SupabaseCorpusSnapshotStore(
        url_env="LOCAL_SUPABASE_URL", service_key_env="LOCAL_SUPABASE_SERVICE_KEY"
    )
    resolver = StudioCorpusResolver(courses, snapshots)
    payload = course_payload()
    payload["id"] = course_id
    course = Course.model_validate(payload)
    reference = CorpusReference(course_id=course_id)
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as db:
        try:
            db.execute("insert into auth.users(id) values (%s),(%s)", (owner, other))
            courses.save(course, owner_id=owner)
            first = await resolver.resolve(reference, owner_id=owner, run_id="first")
            second = await resolver.resolve(reference, owner_id=owner, run_id="second")
            assert first.source.digest == second.source.digest
            row = db.execute(
                "select payload from live_corpus_snapshots where owner_id=%s and course_id=%s",
                (owner, course_id),
            ).fetchall()
            assert len(row) == 1
            assert row[0][0]["source"]["runId"] == "first"
            assert row[0][0]["sections"][1]["answerKey"] == "PRIVATE KEY"
            assert not db.execute(
                "select has_table_privilege('authenticated', "
                "'public.live_corpus_snapshots', 'SELECT')"
            ).fetchone()[0]
            for role in ("anon", "authenticated"):
                with db.transaction():
                    db.execute(sql.SQL("set local role {}").format(sql.Identifier(role)))
                    with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
                        db.execute("select payload from public.live_corpus_snapshots")
            with pytest.raises(CorpusUnavailableError):
                await resolver.resolve(reference, owner_id=other, run_id="foreign")
            with pytest.raises(FileNotFoundError):
                snapshots.load(
                    SnapshotKey(
                        owner_id=other,
                        course_id=course_id,
                        digest=first.source.digest,
                        adapter_version="studio-v1",
                        schema_version="1",
                    )
                )
            course.modules[0].lessons[0].segments.activate.prose = "Revision two"
            courses.save(course, owner_id=owner)
            third = await resolver.resolve(reference, owner_id=owner, run_id="third")
            assert third.source.digest != first.source.digest
            assert (
                len(
                    db.execute(
                        "select digest from live_corpus_snapshots where owner_id=%s", (owner,)
                    ).fetchall()
                )
                == 2
            )
            original = snapshots.load(
                SnapshotKey(
                    owner_id=owner,
                    course_id=course_id,
                    digest=first.source.digest,
                    adapter_version="studio-v1",
                    schema_version="1",
                )
            )
            assert original == first
            with pytest.raises(PersistenceError, match="corpus snapshot insert failed"):
                snapshots.save(first, owner_id=other)
            altered = first.model_copy(update={"caveats": ("Do not overwrite",)})
            assert snapshots.save(altered, owner_id=owner) == original
            assert db.execute(
                "select relrowsecurity from pg_class "
                "where oid='public.live_corpus_snapshots'::regclass"
            ).fetchone()[0]
            assert not db.execute(
                "select has_table_privilege('service_role', "
                "'public.live_corpus_snapshots', 'UPDATE')"
            ).fetchone()[0]
            courses.delete(course_id, owner_id=owner)
            with pytest.raises(CorpusUnavailableError):
                await resolver.resolve(reference, owner_id=owner, run_id="deleted")
            assert (
                db.execute(
                    "select count(*) from live_corpus_snapshots where owner_id=%s", (owner,)
                ).fetchone()[0]
                == 0
            )
        finally:
            db.execute("delete from public.courses where id=%s and user_id=%s", (course_id, owner))
            db.execute("delete from auth.users where id in (%s,%s)", (owner, other))


@pytest.mark.parametrize("field", ["courseId", "digest", "adapterVersion", "schemaVersion"])
@pytest.mark.parametrize("variant", ["missing", "null"])
def test_snapshot_identity_cannot_be_missing_or_null(field: str, variant: str) -> None:
    owner, course_id = str(uuid4()), uuid4().hex
    digest = "b" * 64
    payload = {
        "source": {"courseId": course_id, "digest": digest, "adapterVersion": "studio-v1"},
        "schemaVersion": "1",
    }
    identity = payload if field == "schemaVersion" else payload["source"]
    if variant == "missing":
        identity.pop(field)
    else:
        identity[field] = None
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as db:
        try:
            db.execute("insert into auth.users(id) values (%s)", (owner,))
            db.execute(
                "insert into public.courses(id,user_id,status,payload) values (%s,%s,%s,%s)",
                (course_id, owner, "published", Jsonb({"id": course_id})),
            )
            with db.transaction():
                db.execute("set local role service_role")
                with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
                    db.execute(
                        "insert into public.live_corpus_snapshots "
                        "(owner_id,course_id,digest,adapter_version,schema_version,payload) "
                        "values (%s,%s,%s,%s,%s,%s)",
                        (owner, course_id, digest, "studio-v1", "1", Jsonb(payload)),
                    )
        finally:
            db.execute("delete from public.courses where id=%s and user_id=%s", (course_id, owner))
            db.execute("delete from auth.users where id=%s", (owner,))
