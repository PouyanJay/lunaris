"""Cold sessions retain a text fallback; a published asset is selected on the next session turn."""

import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from lunaris_api.live.session.prefetch_registry import prefetch_registry
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, MemoryGraphStore
from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore, StubGrader, StubTutor
from lunaris_live.sims.registry.cache_key import sim_cache_key
from lunaris_live.sims.registry.schema.asset import SimAsset
from lunaris_live.sims.runtime.materials import SimMaterials
from lunaris_live.sims.schema.verified_bundle import VerifiedBundle

ROOT = Path(__file__).resolve().parents[4]


async def test_cold_session_queues_then_next_session_mounts_the_published_instrument():
    result = json.loads(
        (
            ROOT / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
        ).read_text()
    )
    bundle = VerifiedBundle.model_validate(result["bundle"])
    criterion = MasteryCriterion(
        kind="manipulate", statement=bundle.spec.contract.objective, needs_sim=True
    )
    node = ConceptNode(id="n", name="Doubling", definition="y=2x", mastery_criteria=[criterion])
    graph = ConceptGraph(graph_id="g", topic="Functions", nodes=[node], topo_order=["n"])
    owner = str(uuid4())
    graphs, sessions, known = MemoryGraphStore(), MemorySessionStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id=owner)
    assets, queue = Mock(), Mock()
    assets.find.return_value = []
    queue.enqueue.return_value = "queued"
    runtime = SimMaterials(assets, queue)
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=known,
        tutor=StubTutor(),
        grader=StubGrader(),
        sim_materials=runtime,
        session_budget_s=1800,
    )
    cold = await service.start("g", session_id="cold", owner_id=owner)
    assert cold.turns[0].criterion is None
    await prefetch_registry().settled()
    queue.enqueue.assert_called_once()
    asset = SimAsset(
        id=uuid4(),
        owner_id=owner,
        cache_key=sim_cache_key(node, criterion),
        bundle=bundle,
        calls=result["calls"],
    )
    assets.find.return_value = [asset]
    warm = await service.start("g", session_id="warm", owner_id=owner)
    assert warm.turns[0].surface.app_id == str(asset.id)
    assert warm.turns[0].surface.contract == bundle.spec.contract
    assert warm.turns[0].sim_exchanges == []
    await prefetch_registry().settled()
    queue.enqueue.assert_called_once()
    queue.status.return_value = "building"
    assets.find.return_value = []
    status = await service.sim_availability("cold", owner_id=owner)
    assert status.status == "building"
    await service.discard("cold", owner_id=owner)
    status = await service.sim_availability("cold", owner_id=owner)
    assert status.status == "off"
