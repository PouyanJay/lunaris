"""Lunaris Live, Phase 2a — a session, end to end through the API.

A learner opens a session on a compiled graph, the session is persisted, and it comes back with its
first turn. T1 pinned the wiring — web-facing contract → service → ``lunaris_live.session`` → store,
with one ``session_id`` correlating the lot, and a session as a row rather than connection state
(U2) so a reload returns the learner to where they were.

T4 makes the turn real: the move is the director's (T3) over what this learner already knows (T2),
and the words are the tutor's, written over the concept's authored teaching notes. What the API
level proves is that those notes *travel* — compiled into the map, through the store, into the
session, out to the learner — which no test of any one layer can see.

Exercised through the real ASGI app over httpx; the stubs are the compiler behind the graph and the
tutor behind the turn, both real implementations of their protocols.
"""

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.dependencies import resolve_graph_store
from lunaris_api.live.session.dependencies import (
    get_live_grader,
    get_live_session_service,
    get_live_tutor,
)
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptNode, MasteryCriterion
from lunaris_live.session import (
    DirectorMove,
    GraderUnavailableError,
    LessonParts,
    MemoryKnowledgeStore,
    Session,
    SessionFormatError,
    StubGrader,
    StubTutor,
    TurnGrade,
    TutorUnavailableError,
)


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def client_with_a_silent_tutor(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The same app with a tutor that cannot speak — the provider being down, mid-open."""

    class SilentTutor:
        async def teach(
            self,
            move: DirectorMove,
            node: ConceptNode,
            *,
            topic: str,
            criterion: MasteryCriterion | None = None,
            already_said: Sequence[str] = (),
            run_id: str,
        ) -> str:
            raise TutorUnavailableError("provider is down")

        async def illustrate(self, *args: object, **kwargs: object) -> LessonParts:
            """Down for Tier 2's material as well — one provider, one outage. It has to be here at
            all because the loop asks for the material *beside* the words (T5), and a stub narrower
            than ``ITutor`` would fail with a ``TypeError`` that looks nothing like an outage."""
            raise TutorUnavailableError("provider is down")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    app.dependency_overrides[get_live_tutor] = lambda: SilentTutor()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def client_with_an_unreadable_session(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The same app over a store holding a session this build can no longer parse."""

    class UnreadableStore:
        def save(self, session: Session, *, owner_id: str | None = None) -> None: ...

        def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
            raise SessionFormatError(f"session {session_id} is not in a readable format")

    settings = Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_session_service] = lambda: LiveSessionService(
        resolve_graph_store(settings),
        UnreadableStore(),
        knowledge=MemoryKnowledgeStore(),
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def client_with_no_time_left(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The same app with a session budget already spent by the time anyone answers."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        live_session_budget_s=0.001,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def client_with_a_broken_grader(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The same app with a grader that cannot score — the provider being down, mid-session."""

    class BrokenGrader:
        async def grade(
            self,
            answer: str,
            *,
            criterion: MasteryCriterion,
            node: ConceptNode,
            run_id: str,
        ) -> TurnGrade:
            raise GraderUnavailableError("provider is down")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    app.dependency_overrides[get_live_grader] = lambda: BrokenGrader()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _graph(client: httpx.AsyncClient) -> dict:
    """A compiled map for the session to run on — Phase 1's surface, used as given."""
    return (
        await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})
    ).json()


async def test_opening_a_session_returns_its_first_turn(client: httpx.AsyncClient) -> None:
    # Arrange
    graph = await _graph(client)

    # Act
    response = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})

    # Assert — the contract the surface renders: a live session, on a known map, already teaching.
    assert response.status_code == 201, response.text
    session = response.json()
    assert session["graphId"] == graph["graphId"]
    assert session["status"] == "active"
    assert session["turns"], "a session that opens with nothing to show is a loading spinner"

    first = session["turns"][0]
    assert first["seq"] == 1
    # Every turn is a director move plus what the tutor said about it (A2). The move is what makes
    # the transcript auditable — without it a turn is prose nobody can explain the choice of.
    assert first["move"]["kind"] == "introduce"
    assert first["move"]["nodeId"] in {node["id"] for node in graph["nodes"]}
    assert first["move"]["reason"], "a move with no reason cannot be audited (plan §7)"
    assert first["tutor"].strip()

    # The run id has to ride the response: a session is many minutes of work across many turns, and
    # a learner reporting "it went wrong" needs to name it.
    assert response.headers["X-Session-Id"] == session["sessionId"]


async def test_the_opening_turn_teaches_what_the_map_authored(client: httpx.AsyncClient) -> None:
    """The claim no single layer can make: a concept's teaching notes reach the learner.

    Phase 1 pays a model call per concept to author misconceptions — "the wrong models learners
    commonly hold, stated as the learner would believe them" — precisely so the tutor can go after
    the specific wrong idea in front of it. If they stop travelling anywhere between the compiler
    and the transcript, every session silently degrades to a definition read aloud, and the map
    still looks perfect.
    """
    # Arrange
    graph = await _graph(client)

    # Act
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert — the authored text itself, taken from the compiled map rather than restated here, so
    # this cannot pass by agreeing with a copy of the stub.
    taught_on = session["turns"][0]["move"]["nodeId"]
    node = next(n for n in graph["nodes"] if n["id"] == taught_on)
    misconception = node["teachingSpec"]["misconceptions"][0]
    assert misconception in session["turns"][0]["tutor"]


async def test_a_turn_is_correlated_by_the_run_that_produced_it(client: httpx.AsyncClient) -> None:
    """R6: the session carries a ``session_id``, each turn carries its own ``run_id``. A turn is
    now one or more model calls, and the two ids answer different questions — "show me this
    learner's session" and "show me what the tutor was asked on this line".

    Deliberately the *shape* half of the claim: on its own this would pass on a constant. The test
    below it is the binding half, and neither is the whole claim without the other.
    """
    # Arrange
    graph = await _graph(client)

    # Act
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert
    run_id = session["turns"][0]["runId"]
    assert run_id
    assert run_id != session["sessionId"], "a turn's run is not the session it belongs to"


async def test_the_turns_run_id_is_the_one_its_work_logged_under(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Otherwise the id on the turn is decoration. The point of storing it is that somebody holding
    a line of transcript can find what actually happened underneath it — so the id the learner gets
    back has to be the id the work was logged with, at every layer it crossed."""
    # Arrange
    graph = await _graph(client)

    # Act
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert — read off the stdout JSON rather than structlog's capture_logs, which cannot
    # intercept a module logger another test has already cached (house pattern, see
    # test_live_graphs_api.py).
    run_id = session["turns"][0]["runId"]
    correlated = [line for line in _json_log_lines(capsys) if line.get("run_id") == run_id]
    events = {line.get("event") for line in correlated}
    # ``live.session.started`` passes no ids of its own — it can only appear here if the contextvars
    # binding propagated, which is what stops this passing with the binding deleted and the id
    # merely threaded through arguments by hand.
    assert "live.session.started" in events, f"turn {run_id} left no trace; saw {events}"
    assert all(line.get("session_id") == session["sessionId"] for line in correlated), (
        "a turn's run must stay attached to the session it belongs to"
    )


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]


async def test_a_tutor_that_cannot_speak_leaves_no_session_behind(
    client_with_a_silent_tutor: httpx.AsyncClient,
) -> None:
    """A session whose first turn never happened is not a session. Persisting the shell would give
    a learner a resumable transcript with nothing in it — and ``turns`` is what the surface renders,
    so it would read as a session that opened and then went quiet."""
    # Arrange
    graph = await _graph(client_with_a_silent_tutor)

    # Act
    response = await client_with_a_silent_tutor.post(
        "/api/live/sessions", json={"graphId": graph["graphId"]}
    )

    # Assert — retryable (the provider may come back), correlated, and nothing persisted.
    assert response.status_code == 503, response.text
    session_id = response.headers["X-Session-Id"]
    assert session_id
    resumed = await client_with_a_silent_tutor.get(f"/api/live/sessions/{session_id}")
    assert resumed.status_code == 404


async def _answer(
    client: httpx.AsyncClient, session_id: str, answer: str, *, seq: int = 1
) -> httpx.Response:
    """Answer the turn the learner is looking at. The seq is part of the contract (T6): a duplicate
    submit must not be graded against the question that replaced the one it was written for."""
    return await client.post(
        f"/api/live/sessions/{session_id}/turns", json={"answer": answer, "answeringSeq": seq}
    )


async def test_answering_takes_the_session_to_its_next_turn(client: httpx.AsyncClient) -> None:
    """The loop, through the endpoint the surface will drive: the learner answers what the last
    turn asked, and what comes back is a session with one more beat in it."""
    # Arrange
    graph = await _graph(client)
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    asked = opened["turns"][0]
    assert asked["criterion"], "a turn with nothing staged can never be answered"

    # Act
    response = await _answer(client, opened["sessionId"], "I have no idea about any of this.")

    # Assert — the answered turn keeps its question, gains the answer and the verdict on it.
    assert response.status_code == 200, response.text
    session = response.json()
    answered = session["turns"][0]
    assert answered["answer"] == "I have no idea about any of this."
    assert answered["grade"]["kind"] == "not_met"
    assert answered["grade"]["reason"], "a verdict with no reason is not feedback"
    assert len(session["turns"]) == 2


async def test_what_a_learner_demonstrated_outlives_the_session(client: httpx.AsyncClient) -> None:
    """The claim T2 was built for and nothing could prove until now: evidence written by one
    session is read by the next. Without it a learner would be met at the root of the map every
    time, however much they had already shown."""
    # Arrange — answer the opening concept well enough to master it.
    graph = await _graph(client)
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    session_id, first_concept = opened["sessionId"], opened["turns"][0]["move"]["nodeId"]
    statement = opened["turns"][0]["criterion"]["statement"]
    answered = opened
    for _ in range(3):
        answered = (
            await _answer(client, session_id, statement, seq=answered["turns"][-1]["seq"])
        ).json()
        if answered["status"] != "active":
            break

    # Act — a brand new session on the same map.
    reopened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert — it does not start over on the concept they just demonstrated.
    assert reopened["sessionId"] != session_id
    assert reopened["turns"][0]["move"]["nodeId"] != first_concept


async def test_a_session_out_of_time_says_goodbye_rather_than_going_quiet(
    client_with_no_time_left: httpx.AsyncClient,
) -> None:
    """The clock is wall time measured from the row (plan §6, AD9), so it is real across requests
    and survives a reload — before T6 it was hardcoded to zero and the budget was a setting nothing
    could reach. And the ending is a turn: ``status`` is a field, but the transcript is what the
    learner reads, and a session that stopped talking is indistinguishable from one that crashed."""
    # Arrange
    graph = await _graph(client_with_no_time_left)
    opened = (
        await client_with_no_time_left.post(
            "/api/live/sessions", json={"graphId": graph["graphId"]}
        )
    ).json()

    # Act
    session = (await _answer(client_with_no_time_left, opened["sessionId"], "Anything.")).json()

    # Assert — closed, with a goodbye that says why, and the answered turn still behind it.
    assert session["status"] == "closed"
    closing = session["turns"][-1]
    assert closing["move"]["kind"] == "close"
    assert closing["tutor"].strip()
    assert "minutes are up" in closing["tutor"]
    assert session["turns"][-2]["answer"] == "Anything."


async def test_a_session_that_has_closed_does_not_take_another_answer(
    client: httpx.AsyncClient,
) -> None:
    """A stale tab answering into a session the director ended would run it past the bound the
    close exists to enforce. 409: the request is fine, the session's state is not."""
    # Arrange — a map the stub compiles to three concepts, answered until the director closes.
    graph = await _graph(client)
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    session_id = opened["sessionId"]
    session = opened
    for _ in range(12):
        head = session["turns"][-1]
        session = (await _answer(client, session_id, head["tutor"], seq=head["seq"])).json()
        if session["status"] == "closed":
            break
    assert session["status"] == "closed", "the director never ran out of material"

    # Act
    response = await _answer(client, session_id, "One more thing?")

    # Assert
    assert response.status_code == 409, response.text


async def test_an_answer_to_a_question_that_has_moved_on_is_refused(
    client: httpx.AsyncClient,
) -> None:
    """A learner pressing send twice, or a second tab. Without the seq the duplicate is graded
    against the question that replaced the one they were answering — the words land in the record
    under a criterion they were never written for, and the belief that moves is the wrong one."""
    # Arrange — one answer given, so the session is on turn 2.
    graph = await _graph(client)
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    await _answer(client, opened["sessionId"], "First attempt.", seq=1)

    # Act — the same submit arriving again.
    response = await _answer(client, opened["sessionId"], "First attempt.", seq=1)

    # Assert — a conflict with the session's state, not with the learner: reloading is the recovery.
    assert response.status_code == 409, response.text
    resumed = (await client.get(f"/api/live/sessions/{opened['sessionId']}")).json()
    assert len(resumed["turns"]) == 2, "the refused answer must not have taken a turn"


async def test_an_answer_that_names_no_turn_is_refused(client: httpx.AsyncClient) -> None:
    """The seq is part of the contract, not an optimisation a client may skip: omitted, the server
    would have to guess which question was being answered, which is the guess this prevents."""
    # Arrange
    graph = await _graph(client)
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Act / Assert
    response = await client.post(
        f"/api/live/sessions/{opened['sessionId']}/turns", json={"answer": "Something."}
    )
    assert response.status_code == 422


async def test_an_answer_with_nothing_in_it_is_refused_at_the_door(
    client: httpx.AsyncClient,
) -> None:
    """Not graded as a miss. An empty POST is a client bug, and recording it as evidence would
    lower a belief on the strength of somebody's stray keystroke."""
    # Arrange
    graph = await _graph(client)
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Act / Assert — including whitespace, which is the version a real client actually sends: a
    # space passes a raw length check and reaches the grader as an empty answer, which scores as a
    # miss and lowers a belief the director then acts on.
    assert (await _answer(client, opened["sessionId"], "")).status_code == 422
    assert (await _answer(client, opened["sessionId"], "   ")).status_code == 422
    assert (await _answer(client, opened["sessionId"], "x" * 4001)).status_code == 422


async def test_an_answer_that_could_not_be_scored_changes_nothing(
    client_with_a_broken_grader: httpx.AsyncClient,
) -> None:
    """The failure U1's design exists to survive. An outage must never read as a wrong answer — the
    belief the director gates progress on would move against a learner because the provider had a
    bad minute — so the turn is refused whole, retryably, with the transcript untouched."""
    # Arrange
    graph = await _graph(client_with_a_broken_grader)
    opened = (
        await client_with_a_broken_grader.post(
            "/api/live/sessions", json={"graphId": graph["graphId"]}
        )
    ).json()

    # Act
    response = await _answer(client_with_a_broken_grader, opened["sessionId"], "A real attempt.")

    # Assert — retryable, and the session is where it was: one turn, unanswered, ungraded.
    assert response.status_code == 503, response.text
    resumed = (
        await client_with_a_broken_grader.get(f"/api/live/sessions/{opened['sessionId']}")
    ).json()
    assert len(resumed["turns"]) == 1
    assert resumed["turns"][0]["answer"] is None
    assert resumed["turns"][0]["grade"] is None


async def test_answering_a_session_that_is_not_there_is_not_found(
    client: httpx.AsyncClient,
) -> None:
    # Act / Assert
    assert (await _answer(client, "no-such-session", "Anything.")).status_code == 404


async def test_a_session_this_build_cannot_read_is_not_offered_as_a_retry(
    client_with_an_unreadable_session: httpx.AsyncClient,
) -> None:
    """Told apart from storage being down, because the advice differs: an outage ends and a reload
    fixes it, a row written by a schema this build no longer understands never becomes readable. As
    a 503 it would invite a learner to reload forever."""
    # Act
    response = await client_with_an_unreadable_session.get("/api/live/sessions/s1")

    # Assert
    assert response.status_code == 500, response.text
    assert response.headers["X-Session-Id"] == "s1"


async def test_the_first_concept_is_one_with_nothing_before_it(client: httpx.AsyncClient) -> None:
    """The director may not open in the middle of the map. The whole point of Phase 1's ordering is
    that a learner is never shown a concept whose prerequisites they have not met."""
    # Arrange
    graph = await _graph(client)

    # Act
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert
    opened_on = session["turns"][0]["move"]["nodeId"]
    node = next(n for n in graph["nodes"] if n["id"] == opened_on)
    assert node["requires"] == [], f"{opened_on} was taught before its prerequisites"


async def test_a_session_is_a_row_not_a_connection(client: httpx.AsyncClient) -> None:
    """U2: a 25-40 minute session that dies on a refresh cannot be tested end to end, and Phase 1
    already learned this shape once when a dropped stream nearly cancelled its compile (AD12)."""
    # Arrange
    graph = await _graph(client)
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Act — a second request, the way a reloaded tab re-opens the session it was in.
    response = await client.get(f"/api/live/sessions/{opened['sessionId']}")

    # Assert — the same session, at the same turn, not a fresh one.
    assert response.status_code == 200, response.text
    resumed = response.json()
    assert resumed["sessionId"] == opened["sessionId"]
    assert resumed["turns"] == opened["turns"]


async def test_a_session_on_a_map_that_is_not_there_is_not_found(
    client: httpx.AsyncClient,
) -> None:
    # Act
    response = await client.post("/api/live/sessions", json={"graphId": "no-such-map"})

    # Assert — and the id rides the failure. A header set only once the work succeeded would be
    # absent from exactly the responses somebody needs to report, which is the whole point of it.
    assert response.status_code == 404
    assert response.headers["X-Session-Id"]


async def test_another_owners_session_is_not_found(client: httpx.AsyncClient) -> None:
    """A session's existence is owner-scoped information, so a stranger gets 404 rather than 403 —
    the same posture Phase 1 took for graphs."""
    assert (await client.get("/api/live/sessions/no-such-session")).status_code == 404
