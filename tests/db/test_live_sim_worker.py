"""Real session → durable request → supervisor → approved registry → next turn."""

import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import psycopg
import pytest
from lunaris_api.live.session.prefetch_registry import prefetch_registry
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion
from lunaris_live.graph.supabase_graph_store import SupabaseGraphStore
from lunaris_live.session import StubGrader, StubTutor, SupabaseKnowledgeStore, SupabaseSessionStore
from lunaris_live.session.transactions.supabase_backend import SupabaseGraphTransactions
from lunaris_live.sims.registry.supabase_asset_store import SupabaseSimAssetStore
from lunaris_live.sims.runtime.materials import SimMaterials
from lunaris_live.sims.runtime.models.services import SimWorkerServices
from lunaris_live.sims.runtime.models.worker_context import SimWorkerContext
from lunaris_live.sims.runtime.supabase_queue import SupabaseSimQueue
from lunaris_live.sims.runtime.worker import SimWorker
from lunaris_live.sims.schema.build_result import SimBuildResult

from supabase import create_client

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("SUPABASE_TEST_SERVICE_KEY"), reason="Local REST credentials not set"
    ),
]
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("outcome", ["approved", "rejected", "unsuitable"])
async def test_supervisor_publishes_once_and_next_turn_mounts_asset_without_grading_cold_turn(
    outcome,
):
    owner = str(uuid4())
    approved = SimBuildResult.model_validate_json(
        (
            ROOT / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
        ).read_text()
    )
    criterion = MasteryCriterion(
        kind="manipulate", statement=approved.bundle.spec.contract.objective, needs_sim=True
    )
    node = ConceptNode(id="n", name="Doubling", definition="y=2x", mastery_criteria=[criterion])
    graph = ConceptGraph(graph_id=uuid4().hex, topic="Functions", nodes=[node], topo_order=["n"])
    client = create_client(os.environ["SUPABASE_TEST_URL"], os.environ["SUPABASE_TEST_SERVICE_KEY"])
    queue, assets = SupabaseSimQueue(client=client), SupabaseSimAssetStore(client=client)
    graphs, sessions = SupabaseGraphStore(client=client), SupabaseSessionStore(client=client)
    known = SupabaseKnowledgeStore(client=client)
    factory = Mock()
    result = (
        approved
        if outcome == "approved"
        else SimBuildResult(
            status=outcome, elapsed_ms=1, reason="No suitable simulator", calls=approved.calls
        )
    )
    factory.build = AsyncMock(return_value=result)
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=known,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800,
        sim_materials=SimMaterials(assets, queue),
        transactions=SupabaseGraphTransactions(client=client),
    )
    worker = SimWorker(
        SimWorkerServices(queue, assets, factory), context=SimWorkerContext(sessions=sessions)
    )
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as db:
        db.execute("insert into auth.users(id) values (%s)", (owner,))
    try:
        graphs.save(graph, owner_id=owner)
        cold = await service.start(graph.graph_id, session_id=uuid4().hex, owner_id=owner)
        assert cold.turns[0].criterion is None
        await prefetch_registry().settled()
        assert (await service.sim_availability(cold.session_id, owner_id=owner)).status == "queued"
        assert await worker.run_once()
        expected_status = "approved" if outcome == "approved" else "rejected"
        assert (
            await service.sim_availability(cold.session_id, owner_id=owner)
        ).status == expected_status
        warm = await service.answer(
            cold.session_id, "Explain this further", answering_seq=1, owner_id=owner
        )
        assert warm.turns[0].grade is None
        if outcome == "approved":
            assert warm.turns[-1].surface.kind == "sim_app"
        else:
            assert warm.turns[-1].criterion is None
            assert warm.turns[-1].surface is None or warm.turns[-1].surface.kind != "sim_app"
        assert warm.turns[-1].sim_exchanges == []
        await prefetch_registry().settled()
        assert not await worker.run_once()
        factory.build.assert_awaited_once()
        assert all(
            n.evidence_count == 0 for n in known.load(graph.graph_id, owner_id=owner).nodes.values()
        )
    finally:
        with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as db:
            db.execute("delete from auth.users where id=%s", (owner,))
