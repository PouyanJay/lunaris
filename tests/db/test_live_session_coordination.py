"""Independent API service instances share only real Postgres, never a process-local throttle."""

import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from lunaris_api.live.session.service import LiveSessionService
from lunaris_api.live.session.throttle import LiveSessionThrottle
from lunaris_api.live.work_refused import LiveWorkRefusedError
from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion
from lunaris_live.graph.supabase_graph_store import SupabaseGraphStore
from lunaris_live.session import StaleAnswerError, StubGrader, StubTutor
from lunaris_live.session.supabase_knowledge_store import SupabaseKnowledgeStore
from lunaris_live.session.supabase_session_store import SupabaseSessionStore
from lunaris_live.session.transactions.supabase_backend import SupabaseGraphTransactions

from supabase import create_client

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("SUPABASE_TEST_SERVICE_KEY"), reason="Local REST test credentials not set"
    ),
]


class BlockingGrader(StubGrader):
    def __init__(self):
        self.calls = 0
        self.entered = asyncio.Event()
        self.duplicate = asyncio.Event()
        self.release = asyncio.Event()

    async def grade(self, *args, **kwargs):
        self.calls += 1
        self.entered.set()
        if self.calls > 1:
            self.duplicate.set()
        await self.release.wait()
        return await super().grade(*args, **kwargs)


@pytest.fixture
async def replicas():
    owner = str(uuid4())
    graph = ConceptGraph(
        graph_id=uuid4().hex,
        topic="Linear functions",
        topo_order=["double"],
        nodes=[
            ConceptNode(
                id="double",
                name="Doubling",
                definition="Doubling input doubles output.",
                mastery_criteria=[
                    MasteryCriterion(
                        kind="explain", statement="Explain why doubling input doubles output."
                    )
                ],
            )
        ],
    )
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as connection:
        connection.execute("insert into auth.users(id) values (%s)", (owner,))
    grader = BlockingGrader()
    services = []
    for _ in range(2):
        client = create_client(
            os.environ["SUPABASE_TEST_URL"], os.environ["SUPABASE_TEST_SERVICE_KEY"]
        )
        graphs = SupabaseGraphStore(client=client)
        graphs.save(graph, owner_id=owner)
        services.append(
            LiveSessionService(
                graphs,
                SupabaseSessionStore(client=client),
                knowledge=SupabaseKnowledgeStore(client=client),
                tutor=StubTutor(),
                grader=grader,
                session_budget_s=1800,
                throttle=LiveSessionThrottle(open_daily_cap=20),
                transactions=SupabaseGraphTransactions(client=client),
            )
        )
    try:
        yield services, grader, owner, graph.graph_id
    finally:
        grader.release.set()
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as connection:
            connection.execute("delete from auth.users where id=%s", (owner,))


@pytest.mark.parametrize("different_session", [False, True])
async def test_replicas_refuse_a_second_paid_turn_before_grading(replicas, different_session):
    services, grader, owner, graph_id = replicas
    first = await services[0].start(graph_id, session_id=uuid4().hex, owner_id=owner)
    second = (
        await services[1].start(graph_id, session_id=uuid4().hex, owner_id=owner)
        if different_session
        else first
    )
    taking = asyncio.create_task(
        services[0].answer(
            first.session_id, "Doubling input doubles output.", answering_seq=1, owner_id=owner
        )
    )
    await asyncio.wait_for(grader.entered.wait(), timeout=5)
    competing = asyncio.create_task(
        services[1].answer(
            second.session_id, "Doubling input doubles output.", answering_seq=1, owner_id=owner
        )
    )
    duplicate = asyncio.create_task(grader.duplicate.wait())
    try:
        await asyncio.wait({competing, duplicate}, timeout=5, return_when=asyncio.FIRST_COMPLETED)
        assert competing.done() and isinstance(competing.exception(), LiveWorkRefusedError), (
            f"Duplicate billed admissions: {grader.calls}"
        )
        assert grader.calls == 1
    finally:
        grader.release.set()
        duplicate.cancel()
        await asyncio.gather(taking, competing, duplicate, return_exceptions=True)
    stored = await services[0].load(first.session_id, owner_id=owner)
    assert len(stored.turns) == 2
    known = services[0]._knowledge.load(graph_id, owner_id=owner)
    assert known.nodes["double"].evidence_count == 1

    if not different_session:
        with pytest.raises(StaleAnswerError):
            await services[1].answer(
                first.session_id, "Doubling input doubles output.", answering_seq=1, owner_id=owner
            )
        assert grader.calls == 1, "a committed answer was billed again on retry"


@pytest.mark.parametrize("action", ["discard", "delete", "end", "forget"])
async def test_lifecycle_cannot_overwrite_another_replica_turn(replicas, action):
    services, grader, owner, graph_id = replicas
    session = await services[0].start(graph_id, session_id=uuid4().hex, owner_id=owner)
    taking = asyncio.create_task(
        services[0].answer(
            session.session_id, "Doubling input doubles output.", answering_seq=1, owner_id=owner
        )
    )
    await asyncio.wait_for(grader.entered.wait(), timeout=5)
    try:
        with pytest.raises(LiveWorkRefusedError):
            await getattr(services[1], action)(
                graph_id if action == "forget" else session.session_id, owner_id=owner
            )
    finally:
        grader.release.set()
        await taking
    saved = await services[1].load(session.session_id, owner_id=owner)
    assert len(saved.turns) == 2
    assert services[1]._knowledge.load(graph_id, owner_id=owner).nodes["double"].evidence_count == 1


async def test_cancelled_paid_turn_cannot_silently_rebill_on_another_replica(replicas):
    services, grader, owner, graph_id = replicas
    session = await services[0].start(graph_id, session_id=uuid4().hex, owner_id=owner)
    answer = "Doubling input doubles output."
    taking = asyncio.create_task(
        services[0].answer(session.session_id, answer, answering_seq=1, owner_id=owner)
    )
    await asyncio.wait_for(grader.entered.wait(), timeout=5)
    taking.cancel()
    with pytest.raises(asyncio.CancelledError):
        await taking
    with pytest.raises(LiveWorkRefusedError, match="not be charged again"):
        await services[1].answer(session.session_id, answer, answering_seq=1, owner_id=owner)
    assert grader.calls == 1
    with pytest.raises(LiveWorkRefusedError, match="not be charged again"):
        await services[1].stream_answer(
            session.session_id, answer, run_id="uncertain-retry", answering_seq=1, owner_id=owner
        )
    assert len((await services[1].load(session.session_id, owner_id=owner)).turns) == 1
    # A deliberate new answer is a different operation; no stale worker may land over it.
    grader.release.set()
    await services[1].answer(
        session.session_id,
        answer + " Each input has twice the output.",
        answering_seq=1,
        owner_id=owner,
    )
    assert grader.calls == 2
    assert services[1]._knowledge.load(graph_id, owner_id=owner).nodes["double"].evidence_count == 1


async def test_disconnected_stream_keeps_its_lease_until_atomic_persistence(replicas):
    from threading import Event

    services, grader, owner, graph_id = replicas
    session = await services[0].start(graph_id, session_id=uuid4().hex, owner_id=owner)
    backend = services[0]._transactions._backend
    original_commit = backend.commit
    committed = Event()

    def commit(claim, mutation):
        original_commit(claim, mutation)
        committed.set()

    backend.commit = commit
    beats = await services[0].stream_answer(
        session.session_id,
        "Doubling input doubles output.",
        run_id="detached",
        answering_seq=1,
        owner_id=owner,
    )
    await asyncio.wait_for(grader.entered.wait(), timeout=5)
    await beats.aclose()
    try:
        with pytest.raises(LiveWorkRefusedError):
            await services[1].delete(session.session_id, owner_id=owner)
    finally:
        grader.release.set()
    assert await asyncio.to_thread(committed.wait, 5)
    assert len((await services[1].load(session.session_id, owner_id=owner)).turns) == 2


async def test_expiry_rereads_after_admission_then_forget_and_delete_stay_final(replicas):
    from datetime import timedelta

    services, grader, owner, graph_id = replicas
    session = await services[0].start(graph_id, session_id=uuid4().hex, owner_id=owner)
    aged = session.model_copy(update={"started_at": session.started_at - timedelta(hours=1)})
    services[0]._sessions.save(aged, owner_id=owner)
    backend = services[0]._transactions._backend
    held = backend.acquire(graph_id, owner_id=owner)
    try:
        assert (await services[1].load(session.session_id, owner_id=owner)).status.value == "active"
    finally:
        backend.release(held)
    assert (await services[1].load(session.session_id, owner_id=owner)).status.value == "closed"
    await services[1].forget(graph_id, owner_id=owner)
    assert services[0]._knowledge.load(graph_id, owner_id=owner).nodes == {}
    await services[1].delete(session.session_id, owner_id=owner)
    with pytest.raises(FileNotFoundError):
        await services[0].load(session.session_id, owner_id=owner)
    assert grader.calls == 0
