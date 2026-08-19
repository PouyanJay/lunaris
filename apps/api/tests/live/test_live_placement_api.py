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
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from _live_stack import GatedCompiler, agui_answer
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.dependencies import get_live_graph_service, resolve_graph_store
from lunaris_api.live.launched_compiles import LaunchedCompiles
from lunaris_api.live.service import LiveGraphService
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptGraph, GraphCompilationError
from lunaris_live.session import StubInterviewer, StubPriorMapper


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


async def test_an_answer_during_the_compile_continues_the_interview(
    client_with_a_gated_compile: tuple[httpx.AsyncClient, GatedCompiler],
) -> None:
    """T2: the interview reads the answer, keeps it on the question that asked it, grades nothing,
    and asks the next question — while the compile is still in flight (a rendezvous, not a fast
    stub that has already landed). A reload mid-interview finds all of it on the row."""
    client, compiler = client_with_a_gated_compile
    session = (await _placement(client)).json()
    await asyncio.wait_for(compiler.entered.wait(), 5)

    response = await client.post(
        f"/api/live/sessions/{session['sessionId']}/turns",
        json={"answer": "I had a biology class once.", "answeringSeq": 1},
    )

    assert response.status_code == 200, response.text
    advanced = response.json()
    assert advanced["status"] == "placing"
    asked, following = advanced["turns"]
    assert asked["answer"] == "I had a biology class once."
    assert asked["grade"] is None
    assert following["seq"] == 2
    assert following["move"]["kind"] == "place"
    assert following["tutor"].strip().endswith("?")
    assert following["tutor"] != asked["tutor"], "the next question is a different question"
    # The row is the transcript: a reload mid-interview lands back here.
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert [turn["answer"] for turn in reread["turns"]] == ["I had a biology class once.", None]


async def test_an_answer_over_agui_after_the_map_landed_begins_teaching(
    client: httpx.AsyncClient,
) -> None:
    """The other transport, the seam the learner never sees: the answer that closes the interview
    is met with the first lesson, streamed as any turn is, and the state frame says ``active``."""
    session = (await _placement(client)).json()
    await _compiled(client, session["graphId"])

    response = await client.post(
        f"/api/live/sessions/{session['sessionId']}/agui",
        json=agui_answer("I had a biology class once.", run_id="r-place"),
    )

    assert response.status_code == 200, response.text
    events = _events(response.text)
    kinds = [event["type"] for event in events]
    assert kinds[0] == "RUN_STARTED" and kinds[-1] == "RUN_FINISHED"
    assert "TEXT_MESSAGE_CONTENT" in kinds
    snapshot = next(event for event in events if event["type"] == "STATE_SNAPSHOT")["snapshot"]
    assert snapshot["status"] == "active"
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert reread["status"] == "active"
    assert reread["turns"][0]["answer"] == "I had a biology class once."
    assert reread["turns"][-1]["move"]["kind"] == "introduce"
    assert reread["turns"][-1]["criterion"] is not None


async def test_the_interview_that_runs_out_first_warms_and_advances_when_the_map_lands(
    client_with_a_gated_compile: tuple[httpx.AsyncClient, GatedCompiler],
) -> None:
    """The honest wait (plan §15). The offline interviewer asks three questions and stops; with
    the compile still held, the session WARMS: nothing is asked, an answer into it is stale, and
    ``advance`` says 202 until the map lands, then teaches."""
    client, compiler = client_with_a_gated_compile
    session = (await _placement(client)).json()
    await asyncio.wait_for(compiler.entered.wait(), 5)
    url = f"/api/live/sessions/{session['sessionId']}"
    for seq in (1, 2, 3):
        response = await client.post(
            f"{url}/turns", json={"answer": f"A{seq}", "answeringSeq": seq}
        )
        assert response.status_code == 200, response.text
    session = response.json()

    assert session["status"] == "warming"
    assert not session["turns"][-1]["tutor"].rstrip().endswith("?")
    stale = await client.post(f"{url}/turns", json={"answer": "More?", "answeringSeq": 4})
    assert stale.status_code == 409, stale.text
    # And over AG-UI, the same refusal as a *status*, not an error frame on a 200 (P2b AD9).
    over_agui = await client.post(f"{url}/agui", json=agui_answer("More?", run_id="r-warm"))
    assert over_agui.status_code == 409, over_agui.text
    assert over_agui.json()["detail"] == stale.json()["detail"]
    still = await client.post(f"{url}/advance")
    assert still.status_code == 202, still.text
    assert still.headers["X-Session-Id"] == session["sessionId"]

    compiler.release.set()
    await _compiled(client, session["graphId"])
    advanced = await client.post(f"{url}/advance")

    assert advanced.status_code == 200, advanced.text
    taught = advanced.json()
    assert taught["status"] == "active"
    assert taught["turns"][-1]["move"]["kind"] == "introduce"
    assert taught["turns"][-1]["seq"] == 5
    # Advancing again is idempotent: the row as it stands, not another lesson.
    again = await client.post(f"{url}/advance")
    assert again.status_code == 200
    assert len(again.json()["turns"]) == 5


@pytest.fixture
async def client_with_a_failing_compile(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, LaunchedCompiles]]:
    """The same app, its compile plane failing every topic — the model giving up, mid-interview."""

    class Fails:
        async def compile(self, topic: str, **kwargs: object) -> ConceptGraph:
            # A tick, so the launch has returned (and the session exists) before the failure.
            await asyncio.sleep(0)
            raise GraphCompilationError("The model could not decompose this topic.")

        async def extend(self, *args: object, **kwargs: object) -> ConceptGraph:
            raise NotImplementedError

    settings = Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    # One registry across the per-request instances, as the composition root wires it: the launch
    # and the answer that learns of the failure are different requests.
    launched = LaunchedCompiles()
    app.dependency_overrides[get_live_graph_service] = lambda: LiveGraphService(
        Fails(), resolve_graph_store(settings), launched=launched
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client, launched


async def _failed(launched: LaunchedCompiles, graph_id: str) -> None:
    """Meet the failing compile at its end (a rendezvous on the task, not a guess at ticks)."""
    compiling = launched.compiling(graph_id)
    assert compiling is not None, "the compile was launched here and is still running"
    with pytest.raises(GraphCompilationError):
        await compiling


async def test_a_compile_that_fails_closes_the_session_at_the_next_answer(
    client_with_a_failing_compile: tuple[httpx.AsyncClient, LaunchedCompiles],
) -> None:
    """A learner must not be interviewed for a map that will never come. The failure is learned
    from the compile plane (same process, in-process registry) and said in the goodbye, with the
    compile's own reason and the answer that arrived kept where it belongs."""
    client, launched = client_with_a_failing_compile
    session = (await _placement(client)).json()
    await _failed(launched, session["graphId"])

    response = await client.post(
        f"/api/live/sessions/{session['sessionId']}/turns",
        json={"answer": "Not much.", "answeringSeq": 1},
    )

    assert response.status_code == 200, response.text
    closed = response.json()
    assert closed["status"] == "closed"
    assert closed["turns"][0]["answer"] == "Not much."
    goodbye = closed["turns"][-1]
    assert goodbye["move"]["kind"] == "close"
    assert "could not decompose" in goodbye["tutor"]
    assert "Bayes' theorem" in goodbye["tutor"]


async def test_a_poll_that_arrives_before_the_session_can_act_does_not_eat_the_failure(
    client_with_a_failing_compile: tuple[httpx.AsyncClient, LaunchedCompiles],
) -> None:
    """Found in review: a compile failure handed over on first read was consumed by an ``advance``
    that met a still-placing session (a duplicate poll, a retry) and had nothing to do with it —
    the next answer then went on interviewing for a map that would never come. The failure stays
    readable until the session that owns it has closed and said so."""
    client, launched = client_with_a_failing_compile
    session = (await _placement(client)).json()
    await _failed(launched, session["graphId"])
    url = f"/api/live/sessions/{session['sessionId']}"

    early = await client.post(f"{url}/advance")
    assert early.status_code == 200 and early.json()["status"] == "placing"

    response = await client.post(f"{url}/turns", json={"answer": "Not much.", "answeringSeq": 1})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "closed"
    # And once said, the compile plane is done remembering it.
    assert launched.failure_of(session["graphId"]) is None


async def test_a_compile_lost_to_another_process_is_given_up_after_the_deadline(
    tmp_path: Path,
) -> None:
    """The fallback for a compile this process cannot ask about (a replica, a restart): past the
    compile plane's own deadline plus a grace, a warming session is closed rather than left to poll
    forever. Staged with a compile plane that never learns of the launch (a second registry, the
    way a replica is) and a session row aged past the deadline."""
    settings = Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        live_compile_deadline_s=1.0,
        live_compile_grace_s=0.0,
    )
    compiler = GatedCompiler()
    launching = LiveGraphService(
        compiler, resolve_graph_store(settings), launched=LaunchedCompiles()
    )
    unaware = LiveGraphService(compiler, resolve_graph_store(settings), launched=LaunchedCompiles())
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_graph_service] = lambda: launching
    from lunaris_api.live.session.dependencies import get_live_session_service, get_live_tutor
    from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore, StubGrader

    sessions = MemorySessionStore()
    app.dependency_overrides[get_live_session_service] = lambda: LiveSessionService(
        resolve_graph_store(settings),
        sessions,
        knowledge=MemoryKnowledgeStore(),
        tutor=get_live_tutor(settings),
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
        compiles=unaware,
        interviewer=StubInterviewer(),
        mapper=StubPriorMapper(),
        compile_deadline_s=settings.live_compile_deadline_s,
        compile_grace_s=settings.live_compile_grace_s,
    )
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # ``launching`` is not the service the session plane holds, so a launch has to go
            # through it by hand: the session's compile is then one this session plane never saw.
            session = (await _placement(client)).json()
            # Age the row rather than wait on the wall clock: the deadline reads ``started_at``.
            row = sessions.load(session["sessionId"])
            sessions.save(
                row.model_copy(update={"started_at": row.started_at - timedelta(hours=1)})
            )

            response = await client.post(
                f"/api/live/sessions/{session['sessionId']}/turns",
                json={"answer": "Not much.", "answeringSeq": 1},
            )

            assert response.status_code == 200, response.text
            closed = response.json()
            assert closed["status"] == "closed"
            assert "took too long" in closed["turns"][-1]["tutor"]
    finally:
        compiler.release.set()


async def test_a_learner_who_names_concepts_is_checked_on_them_not_taught_them(
    client: httpx.AsyncClient,
) -> None:
    """T3, end to end through the API with the offline mapper. The answer names two of the map's
    three concepts — the root ("Foundations of …") and, because the top concept is named after
    the topic, the top itself — and not the middle one. So: the first lesson is a graded RETRIEVAL
    of the root rather than an introduction of it; the session carries a profile; the claim is on
    the learner's beliefs, where a later session on the same map reads it; and once the root and
    the middle are demonstrated, the claimed top is *checked* (the boundary at the last claim,
    with nothing left to introduce) rather than the session closing on a claim."""
    session = (await _placement(client)).json()
    await _compiled(client, session["graphId"])
    url = f"/api/live/sessions/{session['sessionId']}"

    response = await client.post(
        f"{url}/turns",
        json={
            "answer": "I know the foundations of Bayes' theorem already, from a stats course.",
            "answeringSeq": 1,
        },
    )

    assert response.status_code == 200, response.text
    taught = response.json()
    assert taught["status"] == "active"
    check = taught["turns"][-1]
    assert (check["move"]["kind"], check["move"]["nodeId"]) == (
        "retrieve",
        "bayes-theorem-foundations",
    )
    assert "interview" in check["move"]["reason"].lower()
    assert taught["profile"] and "stats course" in taught["profile"]

    # The claim outlives the session: a session opened on the SAME map by id (P2a's opening) is
    # directed by the same beliefs, so it too checks the root rather than teaching it.
    again = await client.post("/api/live/sessions", json={"graphId": session["graphId"]})
    assert again.status_code == 201, again.text
    first = again.json()["turns"][0]
    assert (first["move"]["kind"], first["move"]["nodeId"]) == (
        "retrieve",
        "bayes-theorem-foundations",
    )

    # Verify the root (the offline grader marks an answer that restates the criterion as MET),
    # then get introduced to the middle and demonstrate it: the top, claimed and never checked, is
    # then checked rather than closed over.
    async def answer_with_the_criterion(current: dict) -> dict:
        standing = current["turns"][-1]
        reply = await client.post(
            f"{url}/turns",
            json={"answer": standing["criterion"]["statement"], "answeringSeq": standing["seq"]},
        )
        assert reply.status_code == 200, reply.text
        return reply.json()

    verified = await answer_with_the_criterion(taught)
    introduced = verified["turns"][-1]
    assert (introduced["move"]["kind"], introduced["move"]["nodeId"]) == (
        "introduce",
        "bayes-theorem-core",
    )
    # One MET from nothing is not mastery: the middle takes two.
    once = await answer_with_the_criterion(verified)
    assert once["turns"][-1]["move"]["nodeId"] == "bayes-theorem-core"
    twice = await answer_with_the_criterion(once)
    boundary = twice["turns"][-1]
    assert (boundary["move"]["kind"], boundary["move"]["nodeId"]) == ("retrieve", "bayes-theorem")


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


def _events(body: str) -> list[dict]:
    """Every AG-UI event in a run's SSE body. Frames carry no ``event:`` line — the type is a field
    inside the payload — so this reads ``data:`` lines only (the encoder's format)."""
    return [
        json.loads(line.removeprefix("data:").strip())
        for line in body.splitlines()
        if line.startswith("data:")
    ]
