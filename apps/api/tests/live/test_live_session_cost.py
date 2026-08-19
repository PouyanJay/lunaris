"""What a session spends, and what stops it spending without end (Phase 2a, T8).

A session is the third thing in this system that can spend money, after a course and a Live map. It
is not either of them: a map outlives every sitting on it and is purged separately, and "what did
this session cost" is a question about one sitting. So it is its own subject in the ledger — which
D2 generalized the rollup key for, precisely so a new spender would be an enum value rather than a
migration on immutable financial rows.

The admission rules follow the same shape as the compile plane's, with one deliberate difference:
only the *opening* is rationed by count. A session is already bounded by its clock and by its own
cost ceiling, and capping turns as well would end sittings that were going well for a reason nobody
could explain to the learner.
"""

import asyncio
import threading
from datetime import UTC, datetime
from pathlib import Path

import httpx
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_cost_event_store, get_subject_cost_store
from lunaris_api.live.dependencies import resolve_graph_store
from lunaris_api.live.session.dependencies import _resolve_session_store
from lunaris_api.live.session.throttle import LiveSessionThrottle
from lunaris_live.session import MemoryKnowledgeStore, StubGrader
from lunaris_runtime.metering import record_cost
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


async def _graph(client: httpx.AsyncClient) -> dict:
    return (await client.post("/api/live/graphs", json={"topic": "How tides work"})).json()


async def test_a_sessions_spend_is_filed_under_the_session(tmp_path: Path) -> None:
    """A cost recorded inside a turn lands on the session, keyed by its own id.

    Filing it under the map would merge every sitting anyone ever has on that map into one total —
    and under the *course* namespace it could collide with a real course id, in append-only rows
    nobody may correct.
    """
    # Arrange — a tutor that costs something, standing in for a real model call.
    from lunaris_api.live.session.dependencies import get_live_tutor
    from lunaris_runtime.schema import CostProvider, CostUnit

    class CostlyTutor:
        async def teach(
            self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
        ):
            record_cost(
                component="live_tutor",
                provider=CostProvider.ANTHROPIC,
                model="claude-opus-4-8",
                usage={CostUnit.INPUT_TOKENS: 1000.0, CostUnit.OUTPUT_TOKENS: 500.0},
            )
            return f"Teaching {node.name}."

    events, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    app.dependency_overrides[get_cost_event_store] = lambda: events
    app.dependency_overrides[get_subject_cost_store] = lambda: rollup
    app.dependency_overrides[get_live_tutor] = lambda: CostlyTutor()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)

        # Act
        session = (
            await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        ).json()

    # Assert
    spend = await rollup.get(
        subject_type=CostSubjectType.LIVE_SESSION, subject_id=session["sessionId"], owner_id=None
    )
    assert spend is not None, "the turn's spend was never filed"
    assert spend.total_amount > 0
    assert spend.subject_type is CostSubjectType.LIVE_SESSION
    assert spend.subject_id == session["sessionId"]


async def test_a_session_that_has_spent_its_ceiling_takes_no_more_turns(tmp_path: Path) -> None:
    """The runaway guard. A session is bounded by its clock, so this only binds when something is
    wrong — and it is read from the ledger's rollup rather than counted a second time in memory,
    because the number already exists and a second count would be a second truth."""
    # Arrange — a ledger already showing this session well past its ceiling.
    events, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(
        tmp_path, live_session_budget_usd=0.01
    )
    app.dependency_overrides[get_cost_event_store] = lambda: events
    app.dependency_overrides[get_subject_cost_store] = lambda: rollup
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)
        session = (
            await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        ).json()
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
            f"/api/live/sessions/{session['sessionId']}/turns",
            json={"answer": "Another one.", "answeringSeq": 1},
        )

    # Assert — refused with words, not a bare 500, and the learner is told their work is kept.
    assert response.status_code == 429, response.text
    assert "cost ceiling" in response.json()["detail"]


async def test_a_learner_cannot_open_sessions_without_end(tmp_path: Path) -> None:
    """Opening is where a runaway starts: a script that opens sessions in a loop pays a tutor call
    every time. The cap is per owner per day, and a refused opening does not spend the allowance it
    was refused by."""
    # Arrange
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path, live_session_daily_cap=2)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)
        opened = [
            (
                await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
            ).status_code
            for _ in range(3)
        ]

    # Assert
    assert opened == [201, 201, 429]


async def test_an_unreadable_ledger_does_not_end_a_lesson(tmp_path: Path) -> None:
    """Fails open, deliberately. This is a cap on money and metering is observability — if a
    degraded ledger could refuse work, a telemetry outage would become a product outage, and the
    learner would be told they are out of budget when in truth nobody knows what they spent."""
    # Arrange
    from lunaris_runtime.persistence import PersistenceError

    class BrokenRollup(InMemorySubjectCostStore):
        async def get(self, **kwargs: object):  # type: ignore[override]
            raise PersistenceError("the ledger is down")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(
        tmp_path, live_session_budget_usd=0.01
    )
    app.dependency_overrides[get_cost_event_store] = lambda: InMemoryCostEventStore()
    app.dependency_overrides[get_subject_cost_store] = lambda: BrokenRollup()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)
        session = (
            await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        ).json()

        # Act
        response = await client.post(
            f"/api/live/sessions/{session['sessionId']}/turns",
            json={"answer": "Something real.", "answeringSeq": 1},
        )

    # Assert
    assert response.status_code == 200, response.text


async def test_a_tenants_session_is_taught_on_their_own_key(tmp_path: Path) -> None:
    """BYOK reaches the *turn*, not just the compile.

    The model client is built on first use inside the tutor, and it reads the key off a contextvar.
    Resolving the tenant's credentials without scoping the call would teach their session on the
    platform's key — money spent on their behalf that they never authorized and cannot see, on a
    surface that spends on every single turn.
    """
    # Arrange — a tutor that reports which key it would actually have used.
    from lunaris_api.dependencies import optional_user_id
    from lunaris_api.live.session.dependencies import get_live_session_service, get_live_tutor
    from lunaris_api.live.session.service import LiveSessionService
    from lunaris_runtime.credentials import resolve_secret

    seen: list[str | None] = []

    class ReportingTutor:
        async def teach(
            self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
        ):
            seen.append(resolve_secret("ANTHROPIC_API_KEY"))
            return f"Teaching {node.name}."

    async def tenant_keys(owner_id: str) -> dict[str, str]:
        return {"ANTHROPIC_API_KEY": f"sk-{owner_id}"}

    settings = _settings(tmp_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[optional_user_id] = lambda: "learner-1"
    app.dependency_overrides[get_live_tutor] = lambda: ReportingTutor()
    app.dependency_overrides[get_live_session_service] = lambda: LiveSessionService(
        resolve_graph_store(settings),
        _resolve_session_store(settings),
        knowledge=MemoryKnowledgeStore(),
        tutor=ReportingTutor(),
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
        credential_resolver=tenant_keys,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)

        # Act — an owned request, which is what BYOK is for.
        opened = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})

    # Assert
    assert opened.status_code == 201, opened.text
    assert seen == ["sk-learner-1"]


async def test_two_answers_at_once_pay_for_one_turn(tmp_path: Path) -> None:
    """The ceiling only means something if the spending is gated before it happens.

    Two answers sent at the same moment both load the same session, both name the turn in front of
    the learner, and both pass every check made against that snapshot — the store's compare-and-set
    settles which one *counts*, but only after both have paid a grader and a tutor. A ceiling read
    from the ledger cannot see spend that has not been drained yet, so the refusal has to happen
    before the billed calls.
    """
    # Arrange — a tutor slow enough that the second request arrives while the first is inside it.
    from lunaris_api.live.session.dependencies import get_live_tutor

    calls = 0

    class SlowTutor:
        async def teach(
            self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
        ):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)
            return f"Teaching {node.name}."

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    app.dependency_overrides[get_live_tutor] = lambda: SlowTutor()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)
        session = (
            await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        ).json()
        opening_calls = calls

        # Act — the same answer, twice, at once.
        answer = {"answer": "It points downhill.", "answeringSeq": 1}
        first, second = await asyncio.gather(
            client.post(f"/api/live/sessions/{session['sessionId']}/turns", json=answer),
            client.post(f"/api/live/sessions/{session['sessionId']}/turns", json=answer),
        )

    # Assert — one turn taken, one refused, and exactly one tutor call paid for.
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert calls - opening_calls == 1


async def test_an_answer_arriving_while_the_last_is_still_being_written_pays_for_nothing(
    tmp_path: Path,
) -> None:
    """The slot has to cover the writes, not only the billed calls (P2b T9, from review).

    Between the tutor answering and the session row landing there are three awaits (the ledger
    drain and two store writes). Released after the model calls alone, the slot is free in that
    window: a retry arriving then reads the *old* head, passes every check made against it, finds
    the slot free, and pays a second grader and tutor for the same turn, and only then loses the
    compare-and-set. The money is gone before the write is refused. So the slot is held until the
    turn is fully persisted, and a retry in that window is told the last answer is still being
    marked (409), which is also true.

    A rendezvous rather than a sleep: the store's ``save`` parks until the second answer has been
    refused, so the second answer provably arrives inside the window whatever the machine's speed.
    """
    # Arrange, a session store whose first save waits to be released, and a counting tutor.
    from lunaris_api.live.session.dependencies import get_live_session_service, get_live_tutor
    from lunaris_api.live.session.service import LiveSessionService
    from lunaris_live.session import MemorySessionStore

    calls = 0

    class CountingTutor:
        async def teach(
            self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
        ):
            nonlocal calls
            calls += 1
            return f"Teaching {node.name}."

    saving = threading.Event()
    release = threading.Event()

    class ParkingStore(MemorySessionStore):
        def save(self, session, *, owner_id=None, expect_turns=None):  # type: ignore[override]
            # Only the turn's save parks; the opening's goes straight through.
            if expect_turns is not None and not saving.is_set():
                saving.set()
                assert release.wait(5), "the test never released the store"
            return super().save(session, owner_id=owner_id, expect_turns=expect_turns)

    settings = _settings(tmp_path)
    tutor = CountingTutor()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_tutor] = lambda: tutor
    service = LiveSessionService(
        resolve_graph_store(settings),
        ParkingStore(),
        knowledge=MemoryKnowledgeStore(),
        tutor=tutor,
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
        throttle=LiveSessionThrottle(open_daily_cap=0),
    )
    app.dependency_overrides[get_live_session_service] = lambda: service
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)
        session = (
            await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        ).json()
        opening_calls = calls
        answer = {"answer": "It points downhill.", "answeringSeq": 1}
        url = f"/api/live/sessions/{session['sessionId']}/turns"

        # Act, the first answer, then a second one sent only once the first is inside its save.
        first = asyncio.create_task(client.post(url, json=answer))
        await asyncio.to_thread(saving.wait, 5)
        second = await client.post(url, json=answer)
        release.set()
        first_response = await first

    # Assert, the retry was refused as busy and paid for nothing.
    assert first_response.status_code == 200, first_response.text
    assert second.status_code == 409, second.text
    assert "still being marked" in second.json()["detail"]
    assert calls - opening_calls == 1


async def test_a_ledger_that_hangs_does_not_hang_the_turn(tmp_path: Path) -> None:
    """Worse than a ledger that fails is one that never answers.

    ``drain_cost_scope`` swallows its own failures but not its own duration, and nothing above this
    imposes a request timeout — so an unbounded read or write would tie the turn up with no
    recovery path at all. A slow ledger must cost telemetry, never the answer somebody is waiting
    on.
    """

    # Arrange — a rollup that never returns, on both the paths a turn touches.
    class HangingRollup(InMemorySubjectCostStore):
        async def get(self, **kwargs: object):  # type: ignore[override]
            await asyncio.sleep(30)
            raise AssertionError("should have been given up on")

        async def upsert(self, **kwargs: object) -> None:  # type: ignore[override]
            await asyncio.sleep(30)
            raise AssertionError("should have been given up on")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(
        tmp_path, live_session_budget_usd=0.01
    )
    app.dependency_overrides[get_cost_event_store] = lambda: InMemoryCostEventStore()
    app.dependency_overrides[get_subject_cost_store] = lambda: HangingRollup()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)

        # Act / Assert — bounded well inside the 30s the store would take, and the turn lands.
        async with asyncio.timeout(10):
            session = (
                await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
            ).json()
            answered = await client.post(
                f"/api/live/sessions/{session['sessionId']}/turns",
                json={"answer": "Something real.", "answeringSeq": 1},
            )

    assert answered.status_code == 200, answered.text


async def test_a_turn_taken_over_the_stream_is_metered_like_any_other(tmp_path: Path) -> None:
    """The new transport must not be a way to be taught for free (Phase 2b, T2, A4).

    Worth its own test rather than trusting the shared code path, because T2 changed *where the turn
    runs*: `stream_answer` hands `_take_and_save` to `asyncio.create_task`, and a task snapshots the
    context at creation. Cost scoping and BYOK both ride contextvars, so "the same function, called
    from a task instead of awaited inline" is exactly the shape that can silently stop attributing
    spend while every other assertion about the turn still passes.

    Both halves are checked: the money lands under this session, and the *tenant's* key is what paid
    for it.
    """
    # Arrange — a tutor that costs something, and reports which key it was handed.
    from lunaris_api.dependencies import optional_user_id
    from lunaris_api.live.session.dependencies import get_live_session_service, get_live_tutor
    from lunaris_api.live.session.service import LiveSessionService
    from lunaris_runtime.credentials import resolve_secret
    from lunaris_runtime.schema import CostProvider, CostUnit

    taught_with: list[str | None] = []

    class CostlyTutor:
        async def teach(
            self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
        ):
            return "".join(
                [fragment async for fragment in self.stream(move, node, topic=topic, run_id=run_id)]
            )

        async def stream(
            self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id=""
        ):
            taught_with.append(resolve_secret("ANTHROPIC_API_KEY"))
            record_cost(
                component="live_tutor",
                provider=CostProvider.ANTHROPIC,
                model="claude-opus-4-8",
                usage={CostUnit.INPUT_TOKENS: 1000.0, CostUnit.OUTPUT_TOKENS: 500.0},
            )
            yield f"Teaching {node.name}. "
            yield "Now you try."

    events, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    settings = _settings(tmp_path)
    tutor = CostlyTutor()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[optional_user_id] = lambda: "learner-1"
    app.dependency_overrides[get_cost_event_store] = lambda: events
    app.dependency_overrides[get_subject_cost_store] = lambda: rollup
    app.dependency_overrides[get_live_tutor] = lambda: tutor
    app.dependency_overrides[get_live_session_service] = lambda: LiveSessionService(
        resolve_graph_store(settings),
        _resolve_session_store(settings),
        knowledge=MemoryKnowledgeStore(),
        tutor=tutor,
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
        cost_event_store=events,
        subject_cost_store=rollup,
        credential_resolver=_tenant_key,
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = await _graph(client)
        session = (
            await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        ).json()
        opening_spend = await rollup.get(
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id=session["sessionId"],
            owner_id="learner-1",
        )
        assert opening_spend is not None

        # Act — the same turn, over AG-UI rather than over POST /turns.
        response = await client.post(
            f"/api/live/sessions/{session['sessionId']}/agui",
            json={
                "threadId": "t",
                "runId": "r",
                "state": {},
                "messages": [{"id": "m1", "role": "user", "content": "Downhill, I think."}],
                "tools": [],
                "context": [],
                "forwardedProps": {},
            },
        )
        assert response.status_code == 200, response.text

    # Assert — the streamed turn added to this session's total, and paid on the tenant's key.
    spend = await rollup.get(
        subject_type=CostSubjectType.LIVE_SESSION,
        subject_id=session["sessionId"],
        owner_id="learner-1",
    )
    assert spend is not None
    assert spend.total_amount > opening_spend.total_amount, (
        "a turn taken over the stream spent nothing, so the new transport is untolled"
    )
    assert taught_with[-1] == "sk-learner-1", (
        "the streamed turn ran outside the credential scope — a BYOK tenant would be taught on the "
        "platform's key, money spent on their behalf they never authorised and cannot see"
    )


async def _tenant_key(owner_id: str) -> dict[str, str]:
    return {"ANTHROPIC_API_KEY": f"sk-{owner_id}"}
