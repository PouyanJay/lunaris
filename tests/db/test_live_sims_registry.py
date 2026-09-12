"""Real persistence, ownership and fenced publication for generated code."""

import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.getenv("SUPABASE_DB_URL"), reason="SUPABASE_DB_URL not set"),
]
ROOT = Path(__file__).resolve().parents[2]
KEY = "a" * 64


def seed_user(db, owner):
    db.execute("insert into auth.users (id) values (%s)", (owner,))


def claim(db, owner=None, public=None, key=KEY):
    db.execute("select public.claim_live_sim(%s,%s,%s)", (owner, public, key))
    return db.fetchone()[0]


def asset(owner=None, public=None, key=KEY):
    raw = json.loads(
        (
            ROOT / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
        ).read_text()
    )
    return {
        "id": str(uuid4()),
        "ownerId": owner,
        "publicSource": public,
        "cacheKey": key,
        "bundle": raw["bundle"],
        "calls": raw["calls"],
        "revoked": False,
    }


def publish(db, token, payload, owner=None, public=None, key=KEY):
    db.execute(
        "select public.finish_live_sim(%s,%s,%s,%s,%s,%s)",
        (owner, public, key, token, "approved", json.dumps(payload)),
    )
    return db.fetchone()[0]


def test_claim_once_and_expired_paid_work_never_rebills(db):
    first = claim(db)
    assert first["status"] == "building" and first["token"]
    assert "token" not in claim(db)
    db.execute(
        "update public.live_sim_builds set expires_at=now()-interval '1 second' where cache_key=%s",
        (KEY,),
    )
    assert claim(db) == {"status": "indeterminate"}
    assert claim(db) == {"status": "indeterminate"}
    with pytest.raises(psycopg.errors.RaiseException, match="stale"):
        publish(db, first["token"], asset())


def test_publication_is_fenced_immutable_and_revocable(db):
    ticket = claim(db)
    payload = asset()
    assert publish(db, ticket["token"], payload)
    db.execute("select payload from public.live_sim_assets where id=%s", (payload["id"],))
    assert db.fetchone()[0] == payload
    db.execute("update public.live_sim_assets set revoked=true where id=%s", (payload["id"],))
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        db.execute("update public.live_sim_assets set payload='{}' where id=%s", (payload["id"],))


def test_public_assets_are_reusable_but_private_assets_stay_owner_scoped(db, as_user):
    mine, theirs = str(uuid4()), str(uuid4())
    seed_user(db, mine)
    seed_user(db, theirs)
    expected = []
    for owner, public in [(mine, None), (theirs, None), (None, "curated:linear-v1"), (None, None)]:
        ticket = claim(db, owner, public)
        payload = asset(owner, public)
        publish(db, ticket["token"], payload, owner, public)
        if owner == mine or public:
            expected.append(payload["id"])
    as_user(db, mine)
    db.execute("select id from public.live_sim_assets")
    assert {str(row[0]) for row in db.fetchall()} == set(expected)


@pytest.mark.parametrize("target", ["assets", "builds", "claim", "finish"])
def test_authenticated_clients_cannot_publish_or_claim(db, as_user, target):
    owner = str(uuid4())
    seed_user(db, owner)
    as_user(db, owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        if target in {"assets", "builds"}:
            db.execute(f"delete from public.live_sim_{target}")
        elif target == "claim":
            claim(db, owner)
        else:
            publish(db, str(uuid4()), asset(owner), owner)


@pytest.mark.parametrize("corruption", ["visual", "behavior", "hash", "scope"])
def test_unverified_or_cross_owner_publication_is_rejected(db, corruption):
    ticket = claim(db)
    payload = asset()
    if corruption == "visual":
        payload["bundle"].pop("visualVerdict")
    elif corruption == "behavior":
        payload["bundle"]["report"]["approved"] = False
    elif corruption == "hash":
        payload["bundle"]["candidate"]["html"] += "modified"
    else:
        payload["ownerId"] = str(uuid4())
    with pytest.raises(psycopg.errors.RaiseException, match="Invalid"):
        publish(db, ticket["token"], payload)


def test_independent_connections_elect_one_paid_builder():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    key = uuid4().hex * 2
    barrier = Barrier(2)

    def compete():
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as connection:
            barrier.wait(timeout=5)
            with connection.cursor() as cursor:
                return claim(cursor, key=key)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: compete(), range(2)))
        assert sum("token" in result for result in results) == 1
        assert all(result["status"] == "building" for result in results)
    finally:
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as connection:
            connection.execute("delete from public.live_sim_builds where cache_key=%s", (key,))


@pytest.mark.parametrize("token", [None, str(uuid4())])
def test_missing_or_wrong_fence_never_publishes(db, token):
    claim(db)
    with pytest.raises(psycopg.errors.RaiseException, match="stale"):
        publish(db, token, asset())
