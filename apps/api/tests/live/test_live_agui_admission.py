"""Lunaris Live, Phase 2b T9, admission holds over the AG-UI transport, and holds as a *status*.

P2a built three rules that keep a session from spending without end: a per-session USD ceiling read
from the ledger's rollup, one turn in flight per session (the duplicate is refused before it has
paid a grader and a tutor), and the answered turn named on every answer (so a late submit is
refused rather than graded against the question that replaced it). Every one of them was written
against ``POST /{id}/turns``. P2b put a second door on the same room, and A4 named the risk exactly:
not that the new transport needs a throttle of its own, but that it walks around the ones already
there.

Two properties per rule, and they are separable:

1. **The rule holds.** A run over ``/agui`` that the REST surface would refuse is refused, nothing
   is paid, nothing moves.
2. **The refusal is a status, in REST's words.** AD9: what can be known before the response begins
   is said on the status line, so a client learns "we did not start a turn" from a 429/409 rather
   than by parsing a 200 for an error frame. The learner-facing sentence is the one
   ``failure_mapping`` gives the REST surface, because which transport their client speaks must not
   change what they are told.

Exercised through the real ASGI app, router, service, throttle, loop and store are the production
ones, with the stub tutor and grader, or a slow/counting stand-in where the claim is about money.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_cost_event_store, get_subject_cost_store
from lunaris_api.live.session.dependencies import get_live_tutor
from lunaris_api.live.session.prefetch_registry import prefetch_registry
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.schema import CostSubjectType, SubjectCost


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        **overrides,  # type: ignore[arg-type]
    )


class CountingTutor:
    """A tutor that counts the lessons it was asked for and, when told to, parks inside one.

    Streams, because that is the path the AG-UI turn takes; ``teach`` is what the opening turn
    calls. ``hold`` is a rendezvous rather than a sleep: a test that needs a second run to arrive
    *while* the first is being taught sets it (after the opening turn, which must not park), waits
    for ``entered``, sends the second, then releases, so the overlap is proven whatever the
    machine's speed.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.hold = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def teach(
        self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
    ):
        return "".join([part async for part in self.stream(move, node, topic=topic, run_id=run_id)])

    async def stream(
        self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id=""
    ) -> AsyncIterator[str]:
        self.calls += 1
        if self.hold and not self.entered.is_set():
            self.entered.set()
            await asyncio.wait_for(self.release.wait(), 5)
        yield f"Teaching {node.name}. "
        yield "Now you try."


def _app(tmp_path: Path, tutor: CountingTutor | None = None, **overrides: object):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path, **overrides)
    if tutor is not None:
        app.dependency_overrides[get_live_tutor] = lambda: tutor
    return app


async def _session(client: httpx.AsyncClient) -> dict[str, Any]:
    graph = (await client.post("/api/live/graphs", json={"topic": "How tides work"})).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


def _run(answer: str, *, forwarded: dict[str, Any] | None = None, run_id: str = "r") -> dict:
    """The body the Node runtime POSTs for one run. ``forwarded`` is the kit's ``forwardedProps``,
    which is where a browser can say which turn it is answering (T9)."""
    return {
        "threadId": "t",
        "runId": run_id,
        "state": {},
        "messages": [{"id": "m1", "role": "user", "content": answer}],
        "tools": [],
        "context": [],
        "forwardedProps": forwarded or {},
    }


# ── the ceiling ────────────────────────────────────────────────────────────────────────────────


async def test_a_session_past_its_ceiling_is_refused_on_the_stream_with_a_status(
    tmp_path: Path,
) -> None:
    """The RED assertion of T9. The ceiling exists so a runaway stops; a second transport that
    did not read it would be the runaway's own door. And it is a 429 with REST's sentence, not a
    200 whose body says something went wrong."""
    # Arrange, a ledger already showing this session well past its ceiling.
    events, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    app = _app(tmp_path, live_session_budget_usd=0.01)
    app.dependency_overrides[get_cost_event_store] = lambda: events
    app.dependency_overrides[get_subject_cost_store] = lambda: rollup
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session = await _session(client)
        # The opening turn's prefetch (P2c T4) drains its own scope when it ends, recomputing the
        # rollup from the ledger: meet it first, or the planted rollup is recomputed away.
        await prefetch_registry().settled()
        await rollup.upsert(
            cost=SubjectCost(
                subject_type=CostSubjectType.LIVE_SESSION,
                subject_id=session["sessionId"],
                total_amount=5.0,
                currency="USD",
                breakdown={},
                price_book_version="test",
                updated_at=datetime.now(UTC),
            ),
            owner_id=None,
        )

        # Act
        response = await client.post(
            f"/api/live/sessions/{session['sessionId']}/agui", json=_run("Another one.")
        )

    # Assert, a status, the same one and the same words REST gives, and no frames at all.
    assert response.status_code == 429, response.text
    assert "cost ceiling" in response.json()["detail"]
    assert "text/event-stream" not in response.headers.get("content-type", "")


# ── one turn at a time ─────────────────────────────────────────────────────────────────────────


async def test_two_runs_at_once_pay_for_one_turn_and_the_loser_is_a_status(
    tmp_path: Path,
) -> None:
    """P2a's AD30 (a session takes one turn at a time) over the new transport. Both runs load the
    same session and pass every check made against that snapshot; the slot is what stops the
    second paying a grader and a tutor for the same turn. And the refusal is a 409 *before* the
    response begins, the second run never gets a 200 whose stream then apologises, in the words
    REST uses for the same double send."""
    # Arrange, a tutor that parks inside the next lesson until the second run has been answered.
    tutor = CountingTutor()
    app = _app(tmp_path, tutor)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session = await _session(client)
        opening_calls = tutor.calls
        tutor.hold = True
        url = f"/api/live/sessions/{session['sessionId']}/agui"

        # Act, the same answer twice: the second sent only once the first is inside the tutor.
        first_run = asyncio.create_task(
            client.post(url, json=_run("It points downhill.", run_id="r1"))
        )
        await asyncio.wait_for(tutor.entered.wait(), 5)
        second = await client.post(url, json=_run("It points downhill.", run_id="r2"))
        tutor.release.set()
        first = await first_run

    # Assert, one turn taken, one refused as a status, exactly one lesson paid for.
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409], (first.text, second.text)
    refused = first if first.status_code == 409 else second
    assert "still being marked" in refused.json()["detail"]
    assert tutor.calls - opening_calls == 1


# ── the answered turn, named on the transport ──────────────────────────────────────────────────


async def test_a_run_naming_a_turn_that_has_moved_on_is_refused_unpaid(tmp_path: Path) -> None:
    """The stale-card hazard T4 parked (AD22). CopilotKit re-renders every card in the thread, so
    a learner can answer one from three turns ago; derived server-side, that answer would be graded
    against whatever question is up *now*. Named in ``forwardedProps.answeringSeq``, it is refused
    the way REST refuses it, 409, "already been answered", and before anything is paid."""
    # Arrange, a session two turns in, so the standing turn is not the first one.
    tutor = CountingTutor()
    app = _app(tmp_path, tutor)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session = await _session(client)
        url = f"/api/live/sessions/{session['sessionId']}/agui"
        advanced = await client.post(url, json=_run("First answer.", run_id="r1"))
        assert advanced.status_code == 200, advanced.text
        standing = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
        assert standing["turns"][-1]["seq"] == 2, "the fixture must have moved past turn 1"
        paid_so_far = tutor.calls

        # Act, an answer to turn 1, which the learner is no longer on.
        stale = await client.post(
            url, json=_run("A late answer to the old card.", forwarded={"answeringSeq": 1})
        )

    # Assert
    assert stale.status_code == 409, stale.text
    assert "already been answered" in stale.json()["detail"]
    assert tutor.calls == paid_so_far, "a stale answer paid for a lesson"


async def test_a_run_naming_the_standing_turn_takes_it(tmp_path: Path) -> None:
    """The positive half, so the check above cannot be satisfied by refusing everything named."""
    tutor = CountingTutor()
    app = _app(tmp_path, tutor)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session = await _session(client)
        url = f"/api/live/sessions/{session['sessionId']}/agui"

        response = await client.post(
            url, json=_run("Downhill, I think.", forwarded={"answeringSeq": 1})
        )
        after = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()

    assert response.status_code == 200, response.text
    assert after["turns"][0]["answer"] == "Downhill, I think."
    assert len(after["turns"]) == 2


async def test_a_run_naming_no_turn_answers_the_standing_one(tmp_path: Path) -> None:
    """A client that says nothing, every AG-UI client written before T9, and the kit's own, is
    still answering the question in front of the learner, derived exactly as T2 derived it."""
    app = _app(tmp_path)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session = await _session(client)
        url = f"/api/live/sessions/{session['sessionId']}/agui"

        response = await client.post(url, json=_run("Downhill, I think."))
        after = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()

    assert response.status_code == 200, response.text
    assert after["turns"][0]["answer"] == "Downhill, I think."


async def test_a_run_carrying_the_kits_own_props_beside_ours_is_still_taken(tmp_path: Path) -> None:
    """``forwardedProps`` is shared ground: the kit puts its own keys there (an ``a2uiAction`` while
    one is in flight, ``a2uiCatalogAvailable`` when a catalog is mounted). Reading ours must not
    mean refusing theirs, or the first kit feature to add a key would refuse every turn."""
    app = _app(tmp_path)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session = await _session(client)
        url = f"/api/live/sessions/{session['sessionId']}/agui"

        response = await client.post(
            url,
            json=_run(
                "Downhill.",
                forwarded={"answeringSeq": 1, "a2uiCatalogAvailable": True, "a2uiAction": {}},
            ),
        )

    assert response.status_code == 200, response.text


async def test_a_run_naming_a_turn_that_is_not_a_turn_is_a_bad_request(tmp_path: Path) -> None:
    """``forwardedProps`` is untyped on the wire, so what arrives there is validated at the door
    like every other input: a seq that is not a positive integer is a 422, not a 500 and not a
    turn taken against a guess."""
    app = _app(tmp_path)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        session = await _session(client)
        url = f"/api/live/sessions/{session['sessionId']}/agui"

        worded = await client.post(
            url, json=_run("Downhill.", forwarded={"answeringSeq": "the first one"})
        )
        # 0 is the snapshot's own "no turns at all", never a turn anyone answered.
        zero = await client.post(url, json=_run("Downhill.", forwarded={"answeringSeq": 0}))
        after = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()

    assert worded.status_code == 422, worded.text
    assert zero.status_code == 422, zero.text
    assert after["turns"][0]["answer"] is None, "a malformed run took a turn"
