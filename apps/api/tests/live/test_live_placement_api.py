"""Lunaris Live, Phase 2c — a session opened on a topic, before its map exists (T1).

Plan §6: the moment a topic arrives two things start together — the compile, and a placement
conversation that absorbs it — so the learner never sees a progress bar. T1 is the walking
skeleton: ``POST /api/live/sessions {topic}`` opens a *placing* session, launches the compile
under the same graph id the session carries, and asks the learner the interviewer's first
question. Every layer is crossed once with the plainest payload: web-facing contract → session
service → ``lunaris_live.session.open_placement`` → store, with the compile plane's task attached.

What is pinned here is the wiring and the correlation — one ``session_id`` in the session's own
logs *and* in the compile's, which runs detached — not the interview (T2), the priors (T3) or what
happens when the map lands (T2). Exercised through the real ASGI app over httpx with the stub
compiler and the stub interviewer, both real implementations of their protocols.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.dependencies import get_live_graph_service, resolve_graph_store
from lunaris_api.live.service import LiveGraphService
from lunaris_live.graph import ConceptGraph, StubGraphCompiler


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _placement(client: httpx.AsyncClient, topic: str = "Bayes' theorem") -> httpx.Response:
    return await client.post("/api/live/sessions", json={"topic": topic})


async def _compiled(client: httpx.AsyncClient, graph_id: str) -> dict:
    """The map, once the detached compile has landed it. Bounded so a compile that never lands
    fails the test rather than hanging it."""
    async with asyncio.timeout(5):
        while True:
            response = await client.get(f"/api/live/graphs/{graph_id}")
            if response.status_code == 200:
                return response.json()
            await asyncio.sleep(0.02)


async def test_a_topic_opens_a_placing_session_with_a_question_not_a_lesson(
    client: httpx.AsyncClient,
) -> None:
    # Act
    response = await _placement(client)

    # Assert — the contract the surface renders: a session, already talking, on a map that is
    # not there yet.
    assert response.status_code == 201, response.text
    session = response.json()
    assert session["status"] == "placing"
    assert session["topic"] == "Bayes' theorem"
    assert session["graphId"], "a placing session names the map it is waiting for"
    assert response.headers["X-Session-Id"] == session["sessionId"]

    (first,) = session["turns"]
    assert first["seq"] == 1
    assert first["move"]["kind"] == "place"
    assert first["move"]["nodeId"] is None
    assert first["move"]["reason"]
    assert first["tutor"].strip().endswith("?")
    # Nothing staged: an interview answer is about the learner, not about a criterion, and it
    # must never become evidence.
    assert first["criterion"] is None
    assert first["surface"] is None


async def test_the_compile_lands_under_the_id_the_session_was_given(
    client: httpx.AsyncClient,
) -> None:
    """The session's graph id is not a placeholder to be swapped later: it is the id the compile
    was launched under, which is what lets a later turn find the map by re-reading the store
    instead of holding process state — and what lets a learner who reloads keep their session."""
    # Arrange
    session = (await _placement(client)).json()

    # Act
    graph = await _compiled(client, session["graphId"])

    # Assert — the map that landed is THIS topic's, under THIS id.
    assert graph["graphId"] == session["graphId"]
    assert graph["topic"] == "Bayes' theorem"
    assert graph["nodes"], "the compile that landed has to be a real map"
    # And the session is still the row it was: placing, its one interview turn. Reading it back
    # is what a reloaded tab does.
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert reread["status"] == "placing"
    assert reread["graphId"] == session["graphId"]
    assert [turn["move"]["kind"] for turn in reread["turns"]] == ["place"]


async def test_the_session_and_its_detached_compile_are_correlated_by_one_session_id(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """R5: the compile runs detached from the request that launched it, in its own task under its
    own run id. If its log lines did not carry the session that launched it, the first "my session
    never started teaching" report would be untriangulable — the compile that failed would be
    findable only by guessing which graph id was whose."""
    # Arrange
    session = (await _placement(client)).json()
    await _compiled(client, session["graphId"])

    # Act
    lines = _json_log_lines(capsys)
    session_id = session["sessionId"]
    turn_run_id = session["turns"][0]["runId"]

    # Assert — the interview turn's own run, bound to the session (contextvars, not arguments:
    # ``live.session.placing`` passes no ids of its own).
    turn_lines = [line for line in lines if line.get("run_id") == turn_run_id]
    assert "live.session.placing" in {line.get("event") for line in turn_lines}
    assert all(line.get("session_id") == session_id for line in turn_lines)

    # The compile: its own run id (a compile is not a turn), the session's graph id, AND the
    # session id — on the line the compile plane writes with no explicit session argument.
    compile_lines = [
        line
        for line in lines
        if line.get("event") in {"live.graph.compile_started", "live.graph.compile_finished"}
        and line.get("graph_id") == session["graphId"]
    ]
    assert {line.get("event") for line in compile_lines} == {
        "live.graph.compile_started",
        "live.graph.compile_finished",
    }, f"the compile left no full trace; saw {[line.get('event') for line in compile_lines]}"
    assert all(line.get("session_id") == session_id for line in compile_lines), (
        "the detached compile must stay attached to the session that launched it"
    )
    compile_run_ids = {line.get("run_id") for line in compile_lines}
    assert len(compile_run_ids) == 1
    assert compile_run_ids != {turn_run_id}, "a compile is its own run, not the interview turn's"


class GatedCompiler:
    """The stub compiler, held at the door until the test lets it through.

    A rendezvous rather than a sleep: an answer sent while ``entered`` is set and ``release`` is
    not is an answer sent *during* the compile, whatever the machine's speed. Found in review: the
    first version of the test below answered after a stub compile that had already landed, so it
    never exercised the window it claimed to.
    """

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self._inner = StubGraphCompiler()

    async def compile(self, topic: str, **kwargs: object) -> ConceptGraph:
        self.entered.set()
        await asyncio.wait_for(self.release.wait(), 5)
        return await self._inner.compile(topic, **kwargs)  # type: ignore[arg-type]

    async def extend(self, *args: object, **kwargs: object) -> ConceptGraph:
        raise NotImplementedError


@pytest.fixture
async def client_with_a_gated_compile(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, GatedCompiler]]:
    """The same app, its compile plane holding at the door until told to go. Composed over the
    SAME graph store the session plane reads, or the map would land somewhere the session cannot
    see it."""
    settings = Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    compiler = GatedCompiler()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_graph_service] = lambda: LiveGraphService(
        compiler, resolve_graph_store(settings)
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client, compiler
        # Let a compile still held at the door finish, so no task outlives the test.
        compiler.release.set()


async def test_an_answer_during_the_compile_is_refused_honestly_not_as_not_found(
    client_with_a_gated_compile: tuple[httpx.AsyncClient, GatedCompiler],
) -> None:
    """T1 asks; T2 listens. Between the two, an answer typed into the interview must be refused
    in words that are true — and *during* the compile there is no map to read, so a session
    plane that read the map before looking at the status would say "Session not found" (404) to a
    learner whose session it had just opened. Found in review; T2 replaces this test with the
    interview actually continuing."""
    client, compiler = client_with_a_gated_compile
    session = (await _placement(client)).json()
    await asyncio.wait_for(compiler.entered.wait(), 5)
    assert not compiler.release.is_set(), "the fixture must answer while the compile is in flight"

    response = await client.post(
        f"/api/live/sessions/{session['sessionId']}/turns",
        json={"answer": "I had a biology class once.", "answeringSeq": 1},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "The interview isn't taking answers yet."
    # And the session is untouched: still placing, still one turn, no answer recorded.
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert reread["status"] == "placing"
    assert [turn["answer"] for turn in reread["turns"]] == [None]


async def test_an_answer_over_agui_after_the_map_landed_is_refused_in_the_same_words(
    client: httpx.AsyncClient,
) -> None:
    """The other transport, the other moment. Once the map has landed a placing session's graph
    reads fine, and the AG-UI path had its own "not active means closed" guard ahead of the loop's —
    which would have told a CopilotKit learner their session "has already ended" one question in.
    The sentence a learner reads must not depend on which client they speak (P2b AD9)."""
    session = (await _placement(client)).json()
    await _compiled(client, session["graphId"])

    response = await client.post(
        f"/api/live/sessions/{session['sessionId']}/agui",
        json={
            "threadId": "t",
            "runId": "r-place",
            "state": {},
            "messages": [{"id": "m1", "role": "user", "content": "I had a biology class once."}],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "The interview isn't taking answers yet."


async def test_a_start_request_names_a_topic_or_a_map_never_both_or_neither(
    client: httpx.AsyncClient,
) -> None:
    """The two openings are one endpoint (U1) but two different things: a topic starts a compile
    and an interview, a map id starts teaching. A request naming both would have to pick, and one
    naming neither has nothing to open. Both are refused at the door."""
    both = await client.post(
        "/api/live/sessions", json={"topic": "Bayes' theorem", "graphId": "g1"}
    )
    neither = await client.post("/api/live/sessions", json={})
    blank = await client.post("/api/live/sessions", json={"topic": "   "})

    assert both.status_code == 422, both.text
    assert neither.status_code == 422, neither.text
    assert blank.status_code == 422, blank.text


async def test_opening_on_a_map_you_already_have_is_unchanged(client: httpx.AsyncClient) -> None:
    """U1 adds a second way in; it does not move the first. P2a/P2b's opening — a compiled map,
    teaching from turn 1 — has to keep its exact meaning."""
    graph = (await client.post("/api/live/graphs", json={"topic": "Bayes' theorem"})).json()

    response = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})

    assert response.status_code == 201, response.text
    session = response.json()
    assert session["status"] == "active"
    assert session["turns"][0]["move"]["kind"] == "introduce"


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]
