"""Authenticated browser fixture with one shared, actually verified simulator asset."""

import json
from pathlib import Path
from uuid import uuid4

from fastapi.middleware.cors import CORSMiddleware
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import OptionalUserIdDep
from lunaris_api.live.session.dependencies import get_live_session_service
from lunaris_api.live.session.service import LiveSessionService
from lunaris_api.live.session.sim_asset_dependencies import get_sim_asset_store
from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, MemoryGraphStore
from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore, StubGrader, StubTutor
from lunaris_live.sims.reference_coach import ReferenceSimCoach
from lunaris_live.sims.registry.cache_key import sim_cache_key
from lunaris_live.sims.registry.preloaded_registry import PreloadedSimRegistry
from lunaris_live.sims.registry.schema.asset import SimAsset

JWT_SECRET = "browser-fixture-signing-key-with-at-least-sixty-four-bytes-for-tests-only"
ROOT = Path(__file__).resolve().parents[2]
raw = json.loads(
    (
        ROOT / "documentation/evaluations/live-sim-builder-2026-09-11/approved-result.json"
    ).read_text()
)
criterion = MasteryCriterion(
    kind="manipulate", statement=raw["bundle"]["spec"]["contract"]["objective"], needs_sim=True
)
node = ConceptNode(id="n", name="Doubling", definition="y=2x", mastery_criteria=[criterion])
asset = SimAsset(
    id=uuid4(),
    public_source="reviewed:browser-fixture",
    cache_key=sim_cache_key(node, criterion),
    bundle=raw["bundle"],
    calls=raw["calls"],
)
graphs, sessions, knowledge = MemoryGraphStore(), MemorySessionStore(), MemoryKnowledgeStore()


class _Store:
    def load(self, asset_id, *, owner_id):
        if not owner_id or asset_id != str(asset.id) or asset.revoked:
            raise FileNotFoundError()
        return asset


def service(owner_id: OptionalUserIdDep):
    return LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800,
        sims=PreloadedSimRegistry([asset], owner_id=owner_id),
        sim_coach=ReferenceSimCoach(),
    )


app = create_app()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.dependency_overrides[get_settings] = lambda: Settings(
    pipeline="stub",
    course_dir=Path("/tmp/sim-auth-fixture"),
    env_file=Path("/nonexistent/sim-fixture.env"),
    cors_origins=("*",),
    supabase_jwt_secret=JWT_SECRET,
)
app.dependency_overrides[get_live_session_service] = service
app.dependency_overrides[get_sim_asset_store] = lambda: _Store()


@app.post("/test/session")
async def fixture_session(owner_id: OptionalUserIdDep):
    graph = ConceptGraph(graph_id=uuid4().hex, topic="Functions", nodes=[node], topo_order=["n"])
    graphs.save(graph, owner_id=owner_id)
    return await service(owner_id).start(graph.graph_id, session_id=uuid4().hex, owner_id=owner_id)


@app.post("/test/revoke")
async def revoke():
    asset.revoked = True
