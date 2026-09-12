"""Offline HTTP application for the simulator browser test; never imported by production."""

from pathlib import Path
from uuid import uuid4

from fastapi.middleware.cors import CORSMiddleware
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.session.dependencies import get_live_session_service
from lunaris_api.live.session.service import LiveSessionService
from lunaris_api.live.session.throttle import LiveSessionThrottle
from lunaris_live.graph import MemoryGraphStore, StubGraphCompiler
from lunaris_live.graph.schema import MasteryCriterion
from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore, StubGrader, StubTutor
from lunaris_live.sims.reference_app import reference_app
from lunaris_live.sims.reference_coach import ReferenceSimCoach


class _Registry:
    def app_for(self, node, criterion):
        app = reference_app()
        return app if criterion.statement == app.contract.objective else None


app = create_app()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
graphs = MemoryGraphStore()
service = LiveSessionService(
    graphs,
    MemorySessionStore(),
    knowledge=MemoryKnowledgeStore(),
    tutor=StubTutor(),
    grader=StubGrader(),
    session_budget_s=1800,
    sims=_Registry(),
    sim_coach=ReferenceSimCoach(),
    throttle=LiveSessionThrottle(open_daily_cap=100),
)
app.dependency_overrides[get_settings] = lambda: Settings(
    pipeline="stub",
    course_dir=Path("/tmp/lunaris-browser-test"),
    env_file=Path("/nonexistent/lunaris-browser-test.env"),
    cors_origins=("*",),
)
app.dependency_overrides[get_live_session_service] = lambda: service


@app.post("/test/session")
async def fixture_session():
    graph = await StubGraphCompiler().compile(
        "Linear relationships", graph_id=uuid4().hex, run_id="browser-seed"
    )
    first = graph.nodes[0].model_copy(
        update={
            "mastery_criteria": [
                MasteryCriterion(
                    kind="manipulate",
                    statement=reference_app().contract.objective,
                    needs_sim=True,
                )
            ]
        }
    )
    graphs.save(graph.model_copy(update={"nodes": [first, *graph.nodes[1:]]}))
    return await service.start(graph.graph_id, session_id=uuid4().hex)
