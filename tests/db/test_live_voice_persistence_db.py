"""Real PostgreSQL admission, source fencing and private retention boundaries."""

import json
import os
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.getenv("SUPABASE_DB_URL"), reason="SUPABASE_DB_URL not set"),
]


def seed(db):
    owner, sid = str(uuid4()), uuid4().hex
    db.execute("insert into auth.users(id) values (%s)", (owner,))
    db.execute(
        "insert into public.live_sessions(id,user_id,graph_id,status,turn_count,payload) "
        "values (%s,%s,'g','active',1,jsonb_build_object('startedAt',"
        "clock_timestamp(),'turns',%s::jsonb))",
        (
            sid,
            owner,
            json.dumps(
                [{"seq": 1, "runId": "r", "tutor": "Try this.", "answer": None, "simExchanges": []}]
            ),
        ),
    )
    return owner, sid


def claim(db, owner, sid, op=None, **changes):
    request = {
        "operation_id": str(op or uuid4()),
        "kind": "transcription",
        "fingerprint": "a" * 64,
        "turn_seq": 1,
        "source_run_id": "r",
        "exchange_sequence": None,
        "reserve_usd": 0.1,
    }
    request.update(changes)
    db.execute("select public.claim_live_voice(%s,%s,%s)", (owner, sid, json.dumps(request)))
    return db.fetchone()[0]


def test_claim_replays_completed_transcript_and_rejects_changed_identity(db):
    owner, sid = seed(db)
    op = uuid4()
    started = claim(db, owner, sid, op)
    assert started["status"] == "started"
    assert started["source_text"] == "Try this."
    assert claim(db, owner, sid, op)["status"] == "in_progress"
    result = {"text": "My answer", "provider": "test", "model": "test"}
    db.execute(
        "select public.finish_live_voice(%s,%s,%s,%s,%s)",
        (owner, sid, op, started["token"], json.dumps(result)),
    )
    assert db.fetchone()[0]
    replay = claim(db, owner, sid, op)
    assert replay["status"] == "completed"
    assert replay["result"] == result
    assert "token" not in replay
    assert claim(db, owner, sid, op, fingerprint="b" * 64)["status"] == "conflict"


@pytest.mark.parametrize(
    "change", ["owner", "turn", "run", "answer", "closed", "expired", "exchange"]
)
def test_admission_rejects_unauthorized_stale_or_closed_recording(db, change):
    owner, sid = seed(db)
    changes = {}
    if change == "owner":
        owner = str(uuid4())
    if change == "turn":
        changes["turn_seq"] = 2
    if change == "run":
        changes["source_run_id"] = "another"
    if change == "exchange":
        changes["exchange_sequence"] = 1
    if change == "answer":
        db.execute(
            "update public.live_sessions set "
            "payload=jsonb_set(payload,'{turns,0,answer}','\"answered\"') where id=%s",
            (sid,),
        )
    if change == "closed":
        db.execute("update public.live_sessions set status='closed' where id=%s", (sid,))
    if change == "expired":
        db.execute(
            "update public.live_sessions set "
            "payload=jsonb_set(payload,'{startedAt}',to_jsonb(now()-interval '1 hour')) "
            "where id=%s",
            (sid,),
        )
    assert claim(db, owner, sid, **changes)["status"] == (
        "missing" if change == "owner" else "stale"
    )
    db.execute("select count(*) from public.live_voice_operations where session_id=%s", (sid,))
    assert db.fetchone()[0] == 0


def test_closed_goodbye_speech_and_latest_simulator_reaction_are_authoritative(db):
    owner, sid = seed(db)
    db.execute(
        "update public.live_sessions set "
        "payload=jsonb_set(payload,'{turns,0,simExchanges}',%s::jsonb) where id=%s",
        (json.dumps([{"reaction": {"text": "Increase resistance."}}]), sid),
    )
    reaction = claim(db, owner, sid, kind="speech", exchange_sequence=1)
    assert reaction["source_text"] == "Increase resistance."
    assert reaction["audio_key"].endswith(".pcm")
    assert claim(db, owner, sid, kind="speech", exchange_sequence=2)["status"] == "stale"
    db.execute("update public.live_sessions set status='closed' where id=%s", (sid,))
    assert claim(db, owner, sid, kind="speech")["source_text"] == "Try this."


@pytest.mark.parametrize("bound", ["concurrency", "operations", "budget"])
def test_reservations_are_bounded_without_releasing_uncertain_cost(db, bound):
    owner, sid = seed(db)
    opts = (
        {"concurrency": 1}
        if bound == "concurrency"
        else {"operations": 1}
        if bound == "operations"
        else {"budget_usd": 0.15}
    )
    op = uuid4()
    started = claim(db, owner, sid, op, **opts)
    if bound != "concurrency":
        db.execute(
            "select public.finish_live_voice(%s,%s,%s,%s,null)", (owner, sid, op, started["token"])
        )
        assert db.fetchone()[0]
    assert claim(db, owner, sid, **opts)["status"] == "unavailable"


def test_expired_uncertain_operation_never_reclaims_or_accepts_late_completion(db):
    owner, sid = seed(db)
    op = uuid4()
    started = claim(db, owner, sid, op)
    db.execute(
        "update public.live_voice_operations set expires_at=now()-interval '1 second' where "
        "session_id=%s",
        (sid,),
    )
    assert claim(db, owner, sid, op)["status"] == "indeterminate"
    db.execute(
        "select public.finish_live_voice(%s,%s,%s,%s,%s)",
        (
            owner,
            sid,
            op,
            started["token"],
            json.dumps({"text": "late", "provider": "test", "model": "test"}),
        ),
    )
    assert not db.fetchone()[0]


@pytest.mark.parametrize(
    "change", ["wrong_token", "closed", "deleted", "advanced", "expired_session"]
)
def test_completion_is_fenced_against_session_lifecycle(db, change):
    owner, sid = seed(db)
    op = uuid4()
    started = claim(db, owner, sid, op, session_seconds=60)
    token = started["token"]
    if change == "wrong_token":
        token = str(uuid4())
    if change == "closed":
        db.execute("update public.live_sessions set status='closed' where id=%s", (sid,))
    if change == "deleted":
        db.execute("delete from public.live_sessions where id=%s", (sid,))
    if change == "advanced":
        db.execute(
            "update public.live_sessions set payload=jsonb_set(payload,'{turns,0,seq}','2') "
            "where id=%s",
            (sid,),
        )
    if change == "expired_session":
        db.execute(
            "update public.live_sessions set "
            "payload=jsonb_set(payload,'{startedAt}',to_jsonb(now()-interval '2 minutes')) "
            "where id=%s",
            (sid,),
        )
    db.execute(
        "select public.finish_live_voice(%s,%s,%s,%s,%s)",
        (
            owner,
            sid,
            op,
            token,
            json.dumps({"text": "answer", "provider": "test", "model": "test"}),
        ),
    )
    assert not db.fetchone()[0]


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_voice_tables_and_rpcs_are_service_only(db, role):
    db.execute(
        "select table_name from information_schema.tables where table_schema='public' and "
        "table_name like 'live_voice_%'"
    )
    for (table,) in db.fetchall():
        db.execute(
            "select has_table_privilege(%s,%s,'SELECT'),has_table_privilege(%s,%s,'INSERT')",
            (role, table, role, table),
        )
        assert db.fetchone() == (False, False)
    db.execute(
        "select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace where "
        "n.nspname='public' and p.proname like '%live_voice%'"
    )
    for (oid,) in db.fetchall():
        db.execute("select has_function_privilege(%s,%s,'EXECUTE')", (role, oid))
        assert not db.fetchone()[0]
    db.execute("select public from storage.buckets where id='live-voice'")
    assert db.fetchone() == (False,)


def test_audio_tombstone_survives_user_deletion_and_defers_inflight_upload_cleanup(db):
    owner, sid = seed(db)
    started = claim(db, owner, sid, kind="speech")
    db.execute("delete from auth.users where id=%s", (owner,))
    db.execute(
        "select cleanup_after>now(),cleanup_after<now()+interval '10 minutes' from "
        "public.live_voice_audio_cleanup where object_key=%s",
        (started["audio_key"],),
    )
    assert db.fetchone() == (True, True)
    db.execute("select count(*) from public.live_voice_operations where session_id=%s", (sid,))
    assert db.fetchone() == (0,)


def test_independent_database_connections_admit_only_two_simultaneous_operations():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    import psycopg

    barrier = Barrier(8)
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as setup:
        with setup.cursor() as cur:
            owner, sid = seed(cur)
        try:

            def attempt(_):
                with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn, conn.cursor() as cur:
                    barrier.wait(timeout=10)
                    return claim(cur, owner, sid)["status"]

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(attempt, range(8)))
            assert results.count("started") == 2
            assert results.count("unavailable") == 6
        finally:
            setup.execute("delete from auth.users where id=%s", (owner,))


def test_session_deletion_serializes_before_waiting_voice_admission():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    import psycopg

    ready = Event()
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as setup:
        with setup.cursor() as cur:
            owner, sid = seed(cur)
        try:

            def attempt():
                with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn, conn.cursor() as cur:
                    ready.set()
                    return claim(cur, owner, sid)

            with ThreadPoolExecutor(max_workers=1) as pool:
                with setup.transaction():
                    setup.execute(
                        "select id from public.live_sessions where id=%s for update", (sid,)
                    )
                    future = pool.submit(attempt)
                    assert ready.wait(timeout=10)
                    setup.execute("delete from public.live_sessions where id=%s", (sid,))
                assert future.result(timeout=10)["status"] == "missing"
        finally:
            setup.execute("delete from auth.users where id=%s", (owner,))


def test_completed_audio_cleanup_and_transcript_retention_keep_no_rebill_receipt(db):
    owner, sid = seed(db)
    op = uuid4()
    started = claim(db, owner, sid, op, kind="speech")
    result = {
        "audio_key": started["audio_key"],
        "audio_bytes": 2,
        "sample_rate": 24000,
        "provider": "test",
        "model": "test",
    }
    db.execute(
        "select public.finish_live_voice(%s,%s,%s,%s,%s)",
        (owner, sid, op, started["token"], json.dumps(result)),
    )
    assert db.fetchone()[0]
    db.execute(
        "update public.live_voice_operations set created_at=now()-interval '2 days' "
        "where session_id=%s",
        (sid,),
    )
    db.execute("select public.due_live_voice_audio_cleanup()")
    assert db.fetchone()[0] == []
    assert claim(db, owner, sid, op, kind="speech")["status"] == "unavailable"
    db.execute("select result from public.live_voice_operations where session_id=%s", (sid,))
    assert db.fetchone()[0] is None
    db.execute("delete from public.live_sessions where id=%s", (sid,))
    db.execute("select public.due_live_voice_audio_cleanup()")
    assert {"object_key": started["audio_key"]} in db.fetchone()[0]
    db.execute("select public.ack_live_voice_audio_cleanup(%s)", (started["audio_key"],))
    db.execute(
        "select count(*) from public.live_voice_audio_cleanup where object_key=%s",
        (started["audio_key"],),
    )
    assert db.fetchone()[0] == 0


def test_empty_transcript_cannot_be_published_directly_through_rpc(db):
    owner, sid = seed(db)
    op = uuid4()
    started = claim(db, owner, sid, op)
    db.execute(
        "select public.finish_live_voice(%s,%s,%s,%s,%s)",
        (
            owner,
            sid,
            op,
            started["token"],
            json.dumps({"text": "", "provider": "test", "model": "test"}),
        ),
    )
    assert not db.fetchone()[0]
