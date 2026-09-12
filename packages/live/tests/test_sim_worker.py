import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from lunaris_live.graph import ConceptNode, MasteryCriterion
from lunaris_live.session import MemorySessionStore, Session
from lunaris_live.sims.registry.cache_key import sim_cache_key
from lunaris_live.sims.runtime.models.services import SimWorkerServices
from lunaris_live.sims.runtime.models.worker_context import SimWorkerContext
from lunaris_live.sims.runtime.schema.job import SimJob
from lunaris_live.sims.runtime.schema.request import SimRequest
from lunaris_live.sims.runtime.worker import SimWorker
from lunaris_live.sims.schema.build_result import SimBuildResult

APPROVED = (
    Path(__file__).resolve().parents[3]
    / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
)


@pytest.mark.parametrize("expired", [False, True])
async def test_worker_claims_once_and_never_generates_for_an_expired_session(expired):
    owner = str(uuid4())
    node = ConceptNode(id="n", name="Doubling", definition="y=2x")
    criterion = MasteryCriterion(kind="manipulate", statement="Observe doubling", needs_sim=True)
    request = SimRequest(node=node, criterion=criterion, run_id="run")
    job = SimJob(
        owner_id=owner,
        session_id="s",
        cache_key=sim_cache_key(node, criterion),
        token=uuid4(),
        request=request,
    )
    queue, assets, factory = Mock(), Mock(), Mock()
    queue.take.side_effect = [job, None]
    factory.build = AsyncMock(return_value=SimBuildResult(status="unsuitable", elapsed_ms=1))
    sessions = MemorySessionStore()
    sessions.save(
        Session(
            session_id="s",
            graph_id="g",
            started_at=datetime.now(UTC) - timedelta(seconds=2000 if expired else 0),
        ),
        owner_id=owner,
    )
    worker = SimWorker(
        SimWorkerServices(queue, assets, factory), context=SimWorkerContext(sessions=sessions)
    )
    assert await worker.run_once()
    assert not await worker.run_once()
    if expired:
        factory.build.assert_not_called()
    else:
        factory.build.assert_awaited_once_with(node, criterion, run_id="run")
    claim, result = assets.finish.call_args.args
    assert str(claim.owner_id) == owner and claim.public_source is None
    assert str(claim.token) == str(job.token)
    assert result.status in ("unsuitable", "rejected")


async def test_a_stalled_ledger_does_not_hold_the_supervisor_after_publication(monkeypatch):

    from lunaris_live.sims.runtime import worker as module

    monkeypatch.setattr(module, "_DRAIN_TIMEOUT_S", 0.001)
    context = SimWorkerContext(sessions=MemorySessionStore())
    worker = SimWorker(SimWorkerServices(Mock(), Mock(), Mock()), context=context)
    drained = AsyncMock(side_effect=lambda *args: asyncio.Event().wait())

    async def stall(*args):
        await asyncio.Event().wait()

    drained.side_effect = stall
    monkeypatch.setattr(module, "drain_cost_scope", drained)
    await asyncio.wait_for(worker._drain(Mock()), timeout=1)
    drained.assert_awaited_once()


@pytest.mark.parametrize("action", ["close", "delete"])
async def test_session_ending_during_generation_discards_the_approved_asset(action):
    owner = str(uuid4())
    node = ConceptNode(id="n", name="Doubling", definition="y=2x")
    criterion = MasteryCriterion(kind="manipulate", statement="Observe doubling", needs_sim=True)
    job = SimJob(
        owner_id=owner,
        session_id="s",
        cache_key=sim_cache_key(node, criterion),
        token=uuid4(),
        request=SimRequest(node=node, criterion=criterion, run_id="run"),
    )
    queue, assets, factory = Mock(), Mock(), Mock()
    queue.take.return_value = job
    entered, complete = asyncio.Event(), asyncio.Event()
    result = SimBuildResult.model_validate_json(APPROVED.read_text())

    async def build(*args, **kwargs):
        entered.set()
        await complete.wait()
        return result

    factory.build = build
    sessions = MemorySessionStore()
    session = Session(session_id="s", graph_id="g", started_at=datetime.now(UTC))
    sessions.save(session, owner_id=owner)
    worker = SimWorker(
        SimWorkerServices(queue, assets, factory), context=SimWorkerContext(sessions=sessions)
    )
    working = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(entered.wait(), timeout=1)
    if action == "delete":
        sessions.delete("s", owner_id=owner)
    else:
        sessions.save(session.model_copy(update={"status": "closed"}), owner_id=owner)
    complete.set()
    await working
    _, outcome = assets.finish.call_args.args
    assert outcome.status == "rejected" and outcome.bundle is None
    assert "ended" in outcome.reason
