"""Only committed live sessions enqueue bounded, private, single-admission simulator work."""

import json
import os
from uuid import uuid4

import psycopg
import pytest

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.getenv("SUPABASE_DB_URL"), reason="SUPABASE_DB_URL not set"),
]


def session(db):
    owner, sid, graph = str(uuid4()), uuid4().hex, uuid4().hex
    db.execute("insert into auth.users(id) values (%s)", (owner,))
    db.execute(
        "insert into public.live_sessions(id,user_id,graph_id,status,turn_count,payload) "
        "values (%s,%s,%s,'active',0,'{}')",
        (sid, owner, graph),
    )
    return owner, sid, graph


def enqueue(db, owner, sid, key):
    request = {
        "node": {"id": "n"},
        "criterion": {"statement": "Observe doubling"},
        "runId": uuid4().hex,
    }
    db.execute(
        "select public.enqueue_live_sim(%s,%s,%s,%s)", (owner, sid, key, json.dumps(request))
    )
    return db.fetchone()[0]


def test_repeated_prefetch_claims_once_and_never_requeues_uncertain_work(db):
    owner, sid, _ = session(db)
    assert enqueue(db, owner, sid, "a" * 64) == "queued"
    assert enqueue(db, owner, sid, "a" * 64) == "queued"
    db.execute("select public.take_live_sim_request()")
    request = db.fetchone()[0]
    assert request["owner_id"] == owner and request["session_id"] == sid
    assert request["token"]
    db.execute("select public.take_live_sim_request()")
    assert db.fetchone()[0] is None
    db.execute(
        "update public.live_sim_builds set expires_at=now()-interval '1 second' "
        "where cache_key=%s and owner_id=%s",
        ("a" * 64, owner),
    )
    assert enqueue(db, owner, sid, "a" * 64) == "indeterminate"
    db.execute("select public.take_live_sim_request()")
    assert db.fetchone()[0] is None


def test_requests_are_bounded_per_session_and_cannot_spoof_owner(db):
    owner, sid, _ = session(db)
    for key in ["a", "b"]:
        assert enqueue(db, owner, sid, key * 64) == "queued"
    assert enqueue(db, owner, sid, "c" * 64) == "unavailable"
    with pytest.raises(psycopg.errors.RaiseException), db.connection.transaction():
        enqueue(db, str(uuid4()), sid, "d" * 64)


def test_deleted_or_closed_session_cannot_start_queued_paid_work(db):
    owner, sid, _ = session(db)
    assert enqueue(db, owner, sid, "e" * 64) == "queued"
    db.execute("update public.live_sessions set status='closed' where id=%s", (sid,))
    db.execute("select public.take_live_sim_request()")
    assert db.fetchone()[0] is None
    db.execute("select count(*) from public.live_sim_builds where owner_id=%s", (owner,))
    assert db.fetchone()[0] == 0


@pytest.mark.parametrize("name", ["enqueue_live_sim", "take_live_sim_request"])
def test_queue_rpcs_are_service_only(db, as_user, name):
    owner, sid, _ = session(db)
    as_user(db, owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        if name == "enqueue_live_sim":
            enqueue(db, owner, sid, "f" * 64)
        else:
            db.execute("select public.take_live_sim_request()")


def test_daily_paid_quota_survives_session_history_deletion(db):
    owner, sid, _ = session(db)
    for number in range(10):
        db.execute("select public.claim_live_sim(%s,null,%s)", (owner, f"{number:064x}"))
    assert enqueue(db, owner, sid, "f" * 64) == "unavailable"


@pytest.mark.parametrize("stale", ["closed", "expired"])
def test_unpaid_stale_request_can_be_adopted_by_a_new_session(db, stale):
    owner, first, graph = session(db)
    assert enqueue(db, owner, first, "a" * 64) == "queued"
    if stale == "closed":
        db.execute("update public.live_sessions set status='closed' where id=%s", (first,))
    else:
        db.execute(
            "update public.live_sim_requests set created_at=now()-interval '11 minutes' "
            "where owner_id=%s",
            (owner,),
        )
    second = uuid4().hex
    db.execute(
        "insert into public.live_sessions(id,user_id,graph_id,status,turn_count,payload) "
        "values(%s,%s,%s,'active',0,'{}')",
        (second, owner, graph),
    )
    assert enqueue(db, owner, second, "a" * 64) == "queued"
    db.execute("select public.take_live_sim_request()")
    claimed = db.fetchone()[0]
    assert claimed is not None and claimed["session_id"] == second
