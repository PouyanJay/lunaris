"""The simulator talks through the real session API without grading a parameter gesture."""

import json

import httpx
import pytest
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.dependencies import optional_user_id
from lunaris_api.live.dependencies import resolve_graph_store
from lunaris_api.live.session.dependencies import get_live_session_service
from lunaris_api.live.session.service import LiveSessionService
from lunaris_api.live.session.throttle import LiveSessionThrottle
from lunaris_live.graph.schema import MasteryCriterion
from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore, StubGrader, StubTutor
from lunaris_live.sims.reference_app import reference_app
from lunaris_live.sims.reference_coach import ReferenceSimCoach


class ReferenceRegistry:
    def app_for(self, node, criterion):
        app = reference_app()
        return app if criterion.statement == app.contract.objective else None


@pytest.fixture
async def instrument(tmp_path):
    settings = settings_for(tmp_path)
    app = create_app()
    graphs = resolve_graph_store(settings)
    sessions = MemorySessionStore()
    knowledge = MemoryKnowledgeStore()
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800,
        sims=ReferenceRegistry(),
        sim_coach=ReferenceSimCoach(),
        throttle=LiveSessionThrottle(open_daily_cap=20),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_session_service] = lambda: service
    app.dependency_overrides[optional_user_id] = lambda: "learner-a"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        graph = (await client.post("/api/live/graphs", json={"topic": "linear functions"})).json()
        stored = graphs.load(graph["graphId"], owner_id="learner-a")
        first = stored.nodes[0].model_copy(
            update={
                "mastery_criteria": [
                    MasteryCriterion(
                        kind="manipulate",
                        statement=reference_app().contract.objective,
                        needs_sim=True,
                    ),
                ]
            }
        )
        graphs.save(
            stored.model_copy(update={"nodes": [first, *stored.nodes[1:]]}), owner_id="learner-a"
        )
        response = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        assert response.status_code == 201, response.text
        session = response.json()
        assert session["turns"][0]["surface"]["kind"] == "sim_app"
        yield client, session, knowledge, app


def gesture(session, **updates):
    return {
        "version": 1,
        "instanceId": session["turns"][-1]["runId"],
        "turnSeq": 1,
        "sequence": 1,
        "appId": "linear-reference",
        "kind": "param_changed",
        "state": {"x": 4},
        **updates,
    }


async def test_gesture_reaction_is_persisted_without_awarding_mastery(instrument, capsys):
    client, session, knowledge, _ = instrument
    url = f"/api/live/sessions/{session['sessionId']}"
    before = knowledge.load(session["graphId"], owner_id="learner-a")
    capsys.readouterr()
    response = await client.post(f"{url}/sim", json=gesture(session))
    logs = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    assert response.status_code == 200, response.text
    exchange = response.json()
    assert exchange["reaction"]["state"] == {"x": 0}
    assert "You set x to 4" in exchange["reaction"]["text"]
    assert response.headers["X-Session-Id"] == session["sessionId"]
    assert response.headers["X-Request-Id"]
    log = next(log for log in logs if log["event"] == "live.sim.interacted")
    assert log["request_id"] == response.headers["X-Request-Id"]
    assert log["session_id"] == session["sessionId"]
    assert log["run_id"] == exchange["runId"]
    saved = (await client.get(url)).json()
    assert len(saved["turns"]) == 1
    assert saved["turns"][0]["grade"] is None
    assert saved["turns"][0]["simExchanges"] == [exchange]
    assert knowledge.load(session["graphId"], owner_id="learner-a") == before
    replay = await client.post(f"{url}/sim", json=gesture(session))
    assert replay.json() == exchange
    conflict = await client.post(f"{url}/sim", json=gesture(session, state={"x": 5}))
    assert conflict.status_code == 409
    assert knowledge.load(session["graphId"], owner_id="learner-a") == before
    assert len((await client.get(url)).json()["turns"][0]["simExchanges"]) == 1


@pytest.mark.parametrize(
    "update,status",
    [
        ({"state": {"x": 100}}, 422),
        ({"state": {"x": True}}, 422),
        ({"state": {"x": 1.5}}, 422),
        ({"state": {"other": 4}}, 422),
        ({"version": 2}, 422),
        ({"instanceId": "other-frame"}, 409),
        ({"turnSeq": 2}, 409),
        ({"sequence": 2}, 409),
        ({"appId": "other-app"}, 409),
    ],
)
async def test_invalid_or_stale_gestures_do_not_write(instrument, update, status):
    client, session, _, _ = instrument
    url = f"/api/live/sessions/{session['sessionId']}"
    response = await client.post(f"{url}/sim", json=gesture(session, **update))
    assert response.status_code == status, response.text
    assert (await client.get(url)).json()["turns"][0]["simExchanges"] == []


async def test_wrong_owner_and_closed_session_cannot_interact(instrument):
    client, session, _, app = instrument
    url = f"/api/live/sessions/{session['sessionId']}"
    app.dependency_overrides[optional_user_id] = lambda: "learner-b"
    assert (await client.post(f"{url}/sim", json=gesture(session))).status_code == 404
    app.dependency_overrides[optional_user_id] = lambda: "learner-a"
    assert (await client.post(f"{url}/discard")).status_code == 200
    assert (await client.post(f"{url}/sim", json=gesture(session))).status_code == 409


async def test_a_simulator_gesture_has_a_session_endpoint(tmp_path):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_for(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        graph = (await client.post("/api/live/graphs", json={"topic": "linear functions"})).json()
        session = (
            await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        ).json()
        response = await client.post(
            f"/api/live/sessions/{session['sessionId']}/sim",
            json={
                "version": 1,
                "instanceId": session["turns"][-1]["runId"],
                "turnSeq": 1,
                "sequence": 1,
                "appId": "linear-reference",
                "kind": "param_changed",
                "state": {"x": 4},
            },
        )
        # This ordinary text turn has no registered simulator; it must explicitly refuse the
        # gesture, rather than invent a sim, grade a drag, or leave the endpoint unwired.
        assert response.status_code == 409, response.text
