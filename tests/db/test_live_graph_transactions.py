"""Database fencing and receipts survive independent callers and lost workers."""

import json
import os
from uuid import uuid4

import psycopg
import pytest

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.getenv("SUPABASE_DB_URL"), reason="SUPABASE_DB_URL not set"),
]


def acquire(db, graph, owner=None):
    db.execute("select public.acquire_live_graph(%s,%s)", (owner, graph))
    return db.fetchone()[0]


def call(db, name, graph, token, value=None, owner=None):
    from psycopg import sql

    args = [owner, graph, token]
    if value is not None:
        args.append(value)
    query = sql.SQL("select public.{}({})").format(
        sql.Identifier(name), sql.SQL(",").join(sql.Placeholder() for _ in args)
    )
    db.execute(query, args)
    return db.fetchone()[0]


def test_crashed_paid_operation_is_fenced_and_never_automatically_billed_again(db):
    graph = uuid4().hex
    first = acquire(db, graph)
    assert acquire(db, graph) is None
    assert call(db, "begin_live_paid_operation", graph, first, "a" * 64)
    db.execute(
        "update public.live_graph_leases set expires_at=now()-interval '1 second' "
        "where graph_id=%s",
        (graph,),
    )
    second = acquire(db, graph)
    assert second and second != first
    assert not call(db, "begin_live_paid_operation", graph, second, "a" * 64)
    assert not call(db, "renew_live_graph", graph, first)
    call(db, "release_live_graph", graph, first)
    assert acquire(db, graph) is None
    assert call(db, "begin_live_paid_operation", graph, second, "b" * 64)


def test_session_and_knowledge_fail_or_commit_together(db):
    owner, graph, session = str(uuid4()), uuid4().hex, uuid4().hex
    db.execute("insert into auth.users(id) values (%s)", (owner,))
    token = acquire(db, graph, owner)
    mutation = {
        "create": True,
        "session": {"sessionId": session, "graphId": graph, "status": "active", "turns": []},
        "knowledge": {
            "graphId": graph,
            "nodes": {"n": {"nodeId": "n", "estimate": 2, "evidenceCount": 1, "reviewStage": 0}},
        },
    }
    with db.connection.transaction():
        try:
            with db.connection.transaction():
                call(db, "commit_live_graph", graph, token, json.dumps(mutation), owner)
        except psycopg.errors.CheckViolation:
            pass
        else:
            pytest.fail("Invalid knowledge must fail the whole transaction")
        db.execute("select count(*) from public.live_sessions where id=%s", (session,))
        assert db.fetchone()[0] == 0
        mutation["knowledge"]["nodes"]["n"]["estimate"] = 0.5
        assert call(db, "commit_live_graph", graph, token, json.dumps(mutation), owner)
        db.execute("select evidence_count from public.live_knowledge where graph_id=%s", (graph,))
        assert db.fetchone()[0] == 1


@pytest.mark.parametrize(
    "name",
    [
        "acquire_live_graph",
        "lock_live_graph",
        "renew_live_graph",
        "begin_live_paid_operation",
        "commit_live_graph",
        "release_live_graph",
    ],
)
def test_rpc_execute_is_server_only(db, as_user, name):
    owner = str(uuid4())
    db.execute("insert into auth.users(id) values (%s)", (owner,))
    as_user(db, owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        if name == "acquire_live_graph":
            acquire(db, "g", owner)
        else:
            value = (
                "a" * 64
                if name == "begin_live_paid_operation"
                else "{}"
                if name == "commit_live_graph"
                else None
            )
            call(db, name, "g", str(uuid4()), value, owner)


@pytest.mark.parametrize("wrong", [None, str(uuid4())])
def test_null_or_wrong_tokens_cannot_commit(db, wrong):
    graph = uuid4().hex
    acquire(db, graph)
    with pytest.raises(psycopg.errors.RaiseException, match="stale"):
        call(db, "commit_live_graph", graph, wrong, "{}")


@pytest.mark.parametrize("table", ["live_graph_leases", "live_paid_operations"])
def test_lease_and_receipt_tables_are_not_client_readable(db, as_user, table):
    from psycopg import sql

    owner = str(uuid4())
    db.execute("insert into auth.users(id) values (%s)", (owner,))
    as_user(db, owner)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute(sql.SQL("select * from public.{}").format(sql.Identifier(table)))


@pytest.mark.parametrize("attack", ["owner", "graph", "reset", "delete"])
def test_valid_mutations_cannot_cross_scope_or_survive_replacement(db, attack):
    owner, other, graph, session = str(uuid4()), str(uuid4()), uuid4().hex, uuid4().hex
    db.execute("insert into auth.users(id) values (%s),(%s)", (owner, other))
    original = acquire(db, graph, owner)
    payload = {"sessionId": session, "graphId": graph, "status": "closed", "turns": []}
    model = {
        "graphId": graph,
        "nodes": {"n": {"nodeId": "n", "estimate": 0.5, "evidenceCount": 1, "reviewStage": 0}},
    }
    call(
        db,
        "commit_live_graph",
        graph,
        original,
        json.dumps({"create": True, "session": payload, "knowledge": model}),
        owner,
    )
    caller, scope, token = owner, graph, original
    if attack == "owner":
        caller = other
        token = acquire(db, graph, other)
    elif attack == "graph":
        scope = uuid4().hex
        token = acquire(db, scope, owner)
    else:
        db.execute(
            "update public.live_graph_leases set expires_at=now()-interval '1 second' "
            "where graph_id=%s",
            (graph,),
        )
        replacement = acquire(db, graph, owner)
        change = {"forget": True} if attack == "reset" else {"delete_session": session}
        call(db, "commit_live_graph", graph, replacement, json.dumps(change), owner)
    model["nodes"]["n"]["estimate"] = 0.9
    with pytest.raises(psycopg.errors.RaiseException), db.connection.transaction():
        call(
            db,
            "commit_live_graph",
            scope,
            token,
            json.dumps({"session": payload, "knowledge": model, "expected_turns": 0}),
            caller,
        )
    db.execute("select payload from public.live_sessions where id=%s", (session,))
    row = db.fetchone()
    assert row is None if attack == "delete" else row[0] == payload
    db.execute(
        "select estimate,evidence_count from public.live_knowledge "
        "where user_id=%s and graph_id=%s",
        (owner, graph),
    )
    row = db.fetchone()
    assert row is None if attack == "reset" else row == (0.5, 1)
