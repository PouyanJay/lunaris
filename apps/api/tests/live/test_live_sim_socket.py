"""Tier 3 through the API: the simulator mounts, and what it reports is graded (P2b, T6).

The socket has three parts and this is where two of them meet a real app: a registry says a concept
has a simulator, the turn mounts it, and the document the frame loads is actually served. The third
part — the learner acting in the frame — arrives here as an ordinary answer, which is the whole
design: a sim's report is graded by the same separate grader against the same staged criterion, so
Tier 3 adds a surface and not a second way into the learner model.

**The registry is off by default and these tests turn it on**, which is itself part of the contract:
the only simulator that exists is a placeholder, and a placeholder whose report becomes evidence
would grade learners on nothing. So a deployment that has not asked for sims must behave exactly as
P2a did, and that is asserted here too.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from _agui_frames import call_named
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.dependencies import get_live_graph_service
from lunaris_api.live.session.agui.surface_tool import SURFACE_TOOL
from lunaris_api.live.session.dependencies import (
    get_live_grader,
    get_live_interviewer,
    get_live_session_service,
    get_live_sims,
    get_live_tutor,
)
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, MasteryCriterionKind
from lunaris_live.session import (
    STUB_SIM_PATH,
    MemoryKnowledgeStore,
    MemorySessionStore,
    StubGrader,
    StubSimRegistry,
    StubTutor,
)

_GRAPH_ID = "sim-graph"
_NODE_ID = "divergence"
_SIM_STATEMENT = "Drive the learning rate up until the loss diverges, and say where it turned."


def _sim_only_graph() -> ConceptGraph:
    """A map whose one concept can only be demonstrated: the case P2a taught and never checked."""
    return ConceptGraph(
        graph_id=_GRAPH_ID,
        topic="How neural networks learn",
        nodes=[
            ConceptNode(
                id=_NODE_ID,
                name="Divergence",
                definition="What happens when the steps get too big to settle.",
                mastery_criteria=[
                    MasteryCriterion(
                        kind=MasteryCriterionKind.MANIPULATE,
                        statement=_SIM_STATEMENT,
                        needs_sim=True,
                    )
                ],
            )
        ],
        topo_order=[_NODE_ID],
        is_acyclic=True,
    )


class _OneGraphStore:
    """Serves the sim-only map above. Planted rather than compiled, so the registry on/off behaviour
    is isolated from what the compiler happens to author. (Since T10 a hands-on topic compiles to a
    map that reaches this tier through the real path too: `test_live_surface_variants.py`.)"""

    def load(self, graph_id: str, *, owner_id: str | None = None) -> ConceptGraph:
        if graph_id != _GRAPH_ID:
            raise FileNotFoundError(graph_id)
        return _sim_only_graph()

    def save(self, graph: ConceptGraph, *, owner_id: str | None = None) -> None:  # pragma: no cover
        raise NotImplementedError

    def list_for(self, owner_id: str | None = None) -> list[ConceptGraph]:  # pragma: no cover
        return [_sim_only_graph()]


def _app(tmp_path: Path, *, sims: str, registry: Any = None) -> Any:
    """The real app, with the map planted and the registry set the way this deployment would set it.

    The service is composed here rather than letting the container build it, which is the precedent
    the other Live suites already set: the graph store is resolved *inside* the factory rather than
    injected, so it is not something `dependency_overrides` can reach. Everything else — router,
    loop, session store, grader, tutor — is production.
    """
    settings = Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        live_sims=sims,
    )
    # Built ONCE, outside the override, because the stores are in-process: opening a session and
    # answering it are separate requests, and a factory that rebuilt the service per request would
    # hand the second one an empty store and a "session not found" that looks like a routing bug.
    service = LiveSessionService(
        _OneGraphStore(),
        MemorySessionStore(),
        knowledge=MemoryKnowledgeStore(),
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
        # The point of the fixture: the same registry the composition root would build for this
        # setting, so what is under test is the wiring rather than a hand-placed object.
        sims=registry if registry is not None else get_live_sims(settings),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_session_service] = lambda: service
    return app


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """A deployment that mounts simulators."""
    transport = httpx.ASGITransport(app=_app(tmp_path, sims="stub"))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


class _EmptyRegistry:
    """Configured, reachable, and knows about no simulator for this map — Phase 3's steady state."""

    def app_for(self, node: ConceptNode, criterion: MasteryCriterion) -> None:
        return None


@pytest.fixture
async def client_with_an_empty_registry(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_app(tmp_path, sims="stub", registry=_EmptyRegistry()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def client_without_sims(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """Every deployment today: the default, with no registry configured."""
    transport = httpx.ASGITransport(app=_app(tmp_path, sims=""))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _open(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.post("/api/live/sessions", json={"graphId": _GRAPH_ID})
    assert response.status_code == 201, response.text
    return response.json()


# ── the composition root ───────────────────────────────────────────────────────────────────────


def _service_from_the_container(tmp_path: Path, *, sims: str) -> LiveSessionService:
    """The service exactly as FastAPI's container assembles it, with nothing overridden.

    Every other Live API suite substitutes ``get_live_session_service`` wholesale — it has to,
    because the graph store is resolved *inside* the factory rather than injected — with the
    consequence that the factory itself is never run by any test. T0 was that class of bug
    (a dependency declared nowhere, invisible until an image would not boot), so a new argument
    threaded through this function is exactly the thing worth proving rather than assuming.
    """
    settings = Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        live_sims=sims,
    )
    return get_live_session_service(
        settings=settings,
        tutor=get_live_tutor(settings),
        grader=get_live_grader(settings),
        sims=get_live_sims(settings),
        interviewer=get_live_interviewer(settings),
        compiles=get_live_graph_service(settings, cost_event_store=None, subject_cost_store=None),
        cost_event_store=None,
        subject_cost_store=None,
    )


def test_the_container_hands_the_service_a_registry_when_one_is_configured(
    tmp_path: Path,
) -> None:
    """Proves the wiring, not the parts. Deleting ``sims=sims`` from the factory leaves every other
    test in this suite green, because they all build the service by hand."""
    service = _service_from_the_container(tmp_path, sims="stub")

    assert isinstance(service._sims, StubSimRegistry)


def test_the_container_hands_it_none_by_default(tmp_path: Path) -> None:
    """And the default is the one that matters most: a placeholder simulator reaching a learner is
    a placeholder grading them."""
    assert _service_from_the_container(tmp_path, sims="")._sims is None


# ── the mount ──────────────────────────────────────────────────────────────────────────────────


async def test_a_concept_only_a_simulator_can_check_now_opens_with_one(
    client: httpx.AsyncClient,
) -> None:
    """T6's claim through the real API. This map's one concept has no prose criterion at all, so
    before the socket existed the session could only ever hand out a concept map."""
    session = await _open(client)

    surface = session["turns"][-1]["surface"]
    assert surface["kind"] == "sim_app"
    assert surface["url"] == STUB_SIM_PATH
    assert surface["statement"] == _SIM_STATEMENT
    assert session["turns"][-1]["criterion"]["statement"] == _SIM_STATEMENT


async def test_a_registry_that_does_not_cover_this_concept_leaves_it_unchecked(
    client_with_an_empty_registry: httpx.AsyncClient,
) -> None:
    """The shape Phase 3 actually spends its time in, driven through the API rather than only at the
    unit level: a registry is configured and reachable, and simply has no simulator for *this*
    concept yet. It must behave exactly as no registry at all — the concept stays honestly
    uncheckable rather than mounting an empty frame."""
    session = await _open(client_with_an_empty_registry)

    assert session["turns"][-1]["surface"]["kind"] == "concept_map"
    assert session["turns"][-1]["criterion"] is None


async def test_the_same_map_stays_uncheckable_where_no_registry_is_configured(
    client_without_sims: httpx.AsyncClient,
) -> None:
    """The default, and the honest one. The only simulator that exists is a placeholder, and a
    placeholder whose report becomes evidence would grade a learner on nothing — so a deployment
    that has not asked for sims keeps P2a's position exactly."""
    session = await _open(client_without_sims)

    assert session["turns"][-1]["surface"]["kind"] == "concept_map"
    assert session["turns"][-1]["criterion"] is None


async def test_the_mounted_simulator_rides_the_same_tool_call_every_card_does(
    client: httpx.AsyncClient,
) -> None:
    """One tool, five cards, now six (AD14). A separate tool for Tier 3 would be a second
    registration on the browser side, free to drift from the enum that decides which is ever
    called."""
    session = await _open(client)
    events: list[dict[str, Any]] = []
    async with client.stream(
        "POST",
        f"/api/live/sessions/{session['sessionId']}/agui",
        json={
            "threadId": "t",
            "runId": "r",
            "state": {},
            "messages": [],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        },
    ) as response:
        assert response.status_code == 200, await response.aread()
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line.removeprefix("data:").strip()))

    assert call_named(events, SURFACE_TOOL) == session["turns"][-1]["surface"]


# ── the round trip ─────────────────────────────────────────────────────────────────────────────


async def test_what_the_simulator_reports_moves_the_belief(client: httpx.AsyncClient) -> None:
    """The third part of the socket, and the reason it is small: the report goes in through the
    ordinary answer path. No new endpoint, no new evidence semantics, no second grader."""
    session = await _open(client)
    standing = session["turns"][-1]

    answered = await client.post(
        f"/api/live/sessions/{session['sessionId']}/turns",
        json={
            "answer": (
                "Drove the learning rate up until the loss diverges; it turned at about 0.9."
            ),
            "answeringSeq": standing["seq"],
        },
    )

    assert answered.status_code == 200, answered.text
    graded = answered.json()["turns"][0]
    assert graded["grade"] is not None
    assert graded["criterion"]["statement"] == _SIM_STATEMENT


# ── the document the frame loads ───────────────────────────────────────────────────────────────


async def test_the_simulator_the_card_names_is_actually_served(client: httpx.AsyncClient) -> None:
    """The two halves are resolved by different code — the registry writes a URL, the router serves
    a path — so agreement between them is exactly the kind of thing that is true until it is not."""
    session = await _open(client)

    served = await client.get(session["turns"][-1]["surface"]["url"])

    assert served.status_code == 200
    assert served.headers["content-type"].startswith("text/html")
    assert "lunaris.sim.report" in served.text


async def test_the_document_declares_what_it_is_allowed_to_do(client: httpx.AsyncClient) -> None:
    """Belt and braces with the frame's own `sandbox` attribute. That attribute is the host's claim
    about the frame and can be dropped by whoever writes the next surface; this travels with the
    response however it is embedded."""
    served = await client.get(STUB_SIM_PATH)

    policy = served.headers["content-security-policy"]
    assert "default-src 'none'" in policy
    assert "form-action 'none'" in policy
    assert served.headers["x-content-type-options"] == "nosniff"


async def test_the_document_loads_nothing_from_anywhere_else(client: httpx.AsyncClient) -> None:
    """Self-contained is not tidiness here, it is the only thing that works: a frame with an opaque
    origin resolves every relative URL against `null`, so anything external would simply not load —
    and a simulator that silently rendered unstyled would look like a broken session."""
    body = (await client.get(STUB_SIM_PATH)).text

    for external in ("<link", "<img", 'src="http', "src='http", "@import"):
        assert external not in body


async def test_an_unknown_simulator_is_not_found_rather_than_blank(
    client: httpx.AsyncClient,
) -> None:
    """A frame that loaded *something* for an unknown id would show a learner an empty simulator
    and let the turn go on to ask them to demonstrate a criterion in it."""
    assert (await client.get("/api/live/sims/does-not-exist")).status_code == 404
