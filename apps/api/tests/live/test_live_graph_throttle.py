"""What Live refuses to spend, and why (Phase 1, T8c / D4).

A cold compile is minutes of provider calls; an extension is learner-triggered and can be asked for
again and again inside one session. T8b put both on the tenant's ledger, which made the spend
*visible* — this is what makes it *bounded*:

- a compile is admitted per owner, one in flight at a time and a fixed number per day;
- an extension is admitted per graph, a fixed number per day; and
- a graph that has already spent its budget refuses to grow further, read from the rollup the
  ledger keeps rather than from a guess held in memory.

Two claims here are about lifetime rather than counting, and both were written to fail if the
production code stops depending on them: a compile that outlives its stream keeps holding its slot
(T7 deliberately does not cancel it, and a compile that is still spending is still occupying the
runtime), and a compile that fails gives its slot back.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_subject_cost_store
from lunaris_api.live.graph_throttle import (
    LiveGraphThrottle,
    LiveWorkRefusedError,
)
from lunaris_api.live.service import LiveGraphService
from lunaris_live.graph import (
    CompilePhase,
    CompileProgress,
    ConceptGraph,
    ConceptNode,
    GraphCompilationError,
    MemoryGraphStore,
)
from lunaris_runtime.persistence import InMemorySubjectCostStore, PersistenceError
from lunaris_runtime.schema import CostSubjectType, SubjectCost

_TOPIC = "How neural networks learn"


# --------------------------------------------------------------------------------------------
# Through the HTTP edge — that the app actually wires a throttle, and refuses in a way a
# learner's surface can render.
# --------------------------------------------------------------------------------------------


def _client(tmp_path: Path, **limits: object) -> httpx.AsyncClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        **limits,  # type: ignore[arg-type]
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def one_compile_a_day(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(tmp_path, live_compile_daily_cap=1) as client:
        yield client


async def test_the_daily_compile_cap_refuses_a_further_compile(
    one_compile_a_day: httpx.AsyncClient,
) -> None:
    # Arrange — the day's one compile.
    assert (await one_compile_a_day.post("/api/live/graphs", json={"topic": _TOPIC})).status_code

    # Act
    response = await one_compile_a_day.post("/api/live/graphs", json={"topic": "Tides"})

    # Assert — refused, and in the server's own words: a learner who is told only "429" has no way
    # to tell "you have run out for today" from "try again in a second".
    assert response.status_code == 429, response.text
    assert "today" in response.json()["detail"].lower()
    # A refused request is still a request somebody may have to look up.
    assert response.headers["X-Run-Id"]


async def test_the_stream_refuses_before_it_opens_a_body(
    one_compile_a_day: httpx.AsyncClient,
) -> None:
    """The reason admission runs before the compile starts rather than inside it.

    Once an SSE body is open the status is already sent and a refusal can only be a frame — which
    the web reads as "the compile failed", not as "we did not start one". So the stream endpoint
    has to be able to answer 429 as a *status*.
    """
    # Arrange
    await one_compile_a_day.post("/api/live/graphs", json={"topic": _TOPIC})

    # Act
    response = await one_compile_a_day.get("/api/live/graphs/stream", params={"topic": "Tides"})

    # Assert
    assert response.status_code == 429, response.text
    assert not response.headers["content-type"].startswith("text/event-stream")


async def test_the_per_graph_extension_cap_refuses_a_further_extension(
    tmp_path: Path,
) -> None:
    """Extensions are capped per *graph*, not per owner: a session works one map, and the runaway
    this guards against is one conversation asking for the map to grow without end."""
    # Arrange
    async with _client(tmp_path, live_extend_daily_cap=1) as client:
        first = (await client.post("/api/live/graphs", json={"topic": _TOPIC})).json()
        second = (await client.post("/api/live/graphs", json={"topic": "Tides"})).json()
        await client.post(
            f"/api/live/graphs/{first['graphId']}/extend", json={"request": "what about momentum"}
        )

        # Act
        refused = await client.post(
            f"/api/live/graphs/{first['graphId']}/extend", json={"request": "and weight decay?"}
        )
        # The other map has its own allowance — the cap is the graph's, not the process's.
        allowed = await client.post(
            f"/api/live/graphs/{second['graphId']}/extend", json={"request": "and spring tides?"}
        )

    # Assert
    assert refused.status_code == 429, refused.text
    assert refused.headers["X-Run-Id"]
    assert allowed.status_code == 200, allowed.text


# --------------------------------------------------------------------------------------------
# Against the service — the admission semantics themselves.
# --------------------------------------------------------------------------------------------


class ParkedCompiler:
    """A compiler that reports one beat, then parks until the test releases it.

    Lets a test hold a compile genuinely in flight — no sleeps, no timing — which is the only way
    to say anything true about a slot that is occupied *while* work is running.
    """

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.fail = False

    async def compile(
        self, topic: str, *, graph_id: str, run_id: str, on_progress: object = None
    ) -> ConceptGraph:
        self.started.set()
        if on_progress is not None:
            on_progress(CompileProgress(phase=CompilePhase.DECOMPOSING))  # type: ignore[operator]
        await self.release.wait()
        if self.fail:
            raise GraphCompilationError("the model gave us nothing usable")
        return ConceptGraph(
            graph_id=graph_id,
            topic=topic,
            nodes=[ConceptNode(id="a", name="A", definition="A concept.")],
            topo_order=["a"],
            is_acyclic=True,
        )

    async def extend(
        self, graph: ConceptGraph, *, request: str, anchors: list[str], run_id: str
    ) -> ConceptGraph:
        added = ConceptNode(id="b", name="B", definition="Asked for mid-session.")
        return graph.model_copy(
            update={
                "nodes": [*graph.nodes, added],
                "version": graph.version + 1,
                "topo_order": [*graph.topo_order, "b"],
            }
        )


def _throttled(compiler: object, **kwargs: object) -> LiveGraphService:
    return LiveGraphService(
        compiler,  # type: ignore[arg-type]
        MemoryGraphStore(),
        throttle=LiveGraphThrottle(compile_daily_cap=10, compile_max_concurrent=1),
        **kwargs,  # type: ignore[arg-type]
    )


async def test_a_second_compile_while_one_is_running_is_refused() -> None:
    # Arrange
    compiler = ParkedCompiler()
    service = _throttled(compiler)
    running = asyncio.ensure_future(service.compile(_TOPIC, run_id="r1", owner_id="alice"))
    await compiler.started.wait()

    # Act — bounded, because a refusal is supposed to be *immediate*: a compile that is wrongly
    # admitted would park behind the first one forever and this would hang instead of failing.
    with pytest.raises(LiveWorkRefusedError):
        async with asyncio.timeout(2):
            await service.compile("Tides", run_id="r2", owner_id="alice")

    # Assert — and the slot comes back when the first one finishes.
    compiler.release.set()
    await running
    await service.compile("Tides", run_id="r3", owner_id="alice")


async def test_one_learner_s_compile_does_not_block_another_s() -> None:
    """The scarce thing being rationed is a *tenant's* spend, not the process."""
    # Arrange
    compiler = ParkedCompiler()
    service = _throttled(compiler)
    running = asyncio.ensure_future(service.compile(_TOPIC, run_id="r1", owner_id="alice"))
    await compiler.started.wait()

    # Act / Assert — bob is unaffected by alice's compile.
    bob = asyncio.ensure_future(service.compile("Tides", run_id="r2", owner_id="bob"))
    compiler.release.set()
    await asyncio.gather(running, bob)


async def test_a_compile_that_outlives_its_stream_keeps_holding_its_slot() -> None:
    """T7's promise and this task's cost are the same fact seen twice.

    A dropped stream does not cancel the compile behind it — it is minutes of work, it persists
    under the id already handed over, and cancelling it would make a retry pay twice. But a compile
    that is still running is still spending, so the slot has to stay held until the *compile* ends,
    not until the connection does. Releasing on disconnect would let one learner start a second
    three-minute compile while the first is still billing.
    """
    # Arrange — a stream, abandoned mid-compile the way a closed tab abandons one.
    compiler = ParkedCompiler()
    service = _throttled(compiler)
    beats = service.stream(_TOPIC, graph_id="g1", run_id="r1", owner_id="alice")
    assert (await anext(beats))[0] == "progress"
    await beats.aclose()

    # Act / Assert — the compile is still running, so a second one is still refused. Bounded for
    # the same reason as above: a wrongly-admitted compile parks behind the abandoned one, and a
    # hang is a much worse way to learn this than an assertion.
    assert not compiler.release.is_set()
    with pytest.raises(LiveWorkRefusedError):
        async with asyncio.timeout(2):
            await service.compile("Tides", run_id="r2", owner_id="alice")

    # ...and only once the abandoned compile really ends does the slot come back. The abandoned
    # compile is nobody's to await — that is the whole point of it — so this waits for the outcome
    # rather than for a handle, bounded so a slot that never comes back fails instead of hanging.
    compiler.release.set()
    async with asyncio.timeout(5):
        while True:
            try:
                await service.compile("Tides", run_id="r3", owner_id="alice")
                return
            except LiveWorkRefusedError:
                await asyncio.sleep(0.01)


async def test_a_failed_compile_gives_its_slot_back() -> None:
    """Otherwise one bad topic locks a learner out of Live until the process restarts."""
    # Arrange
    compiler = ParkedCompiler()
    compiler.fail = True
    compiler.release.set()
    service = _throttled(compiler)

    # Act
    with pytest.raises(GraphCompilationError):
        await service.compile(_TOPIC, run_id="r1", owner_id="alice")

    # Assert
    compiler.fail = False
    await service.compile("Tides", run_id="r2", owner_id="alice")


async def test_the_daily_cap_counts_finished_compiles_too() -> None:
    """A completed compile has spent its money; releasing the in-flight slot must not refund the
    day's allowance, or the cap only ever bounds concurrency."""
    # Arrange
    compiler = ParkedCompiler()
    compiler.release.set()
    service = LiveGraphService(
        compiler,  # type: ignore[arg-type]
        MemoryGraphStore(),
        throttle=LiveGraphThrottle(compile_daily_cap=2, compile_max_concurrent=1),
    )

    # Act
    await service.compile(_TOPIC, run_id="r1", owner_id="alice")
    await service.compile("Tides", run_id="r2", owner_id="alice")

    # Assert
    with pytest.raises(LiveWorkRefusedError):
        await service.compile("Photosynthesis", run_id="r3", owner_id="alice")


async def test_a_new_day_restores_the_allowance() -> None:
    # Arrange — a clock the test moves, so the reset is proven rather than waited for.
    compiler = ParkedCompiler()
    compiler.release.set()
    today = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    now = today
    service = LiveGraphService(
        compiler,  # type: ignore[arg-type]
        MemoryGraphStore(),
        throttle=LiveGraphThrottle(
            compile_daily_cap=1, compile_max_concurrent=1, clock=lambda: now
        ),
    )
    await service.compile(_TOPIC, run_id="r1", owner_id="alice")
    with pytest.raises(LiveWorkRefusedError):
        await service.compile("Tides", run_id="r2", owner_id="alice")

    # Act
    now = today.replace(day=4)

    # Assert
    await service.compile("Tides", run_id="r3", owner_id="alice")


# --------------------------------------------------------------------------------------------
# The per-graph budget — the cap that is read from the ledger rather than counted in memory.
# --------------------------------------------------------------------------------------------


def _rollup(graph_id: str, *, total: float) -> SubjectCost:
    return SubjectCost(
        subject_type=CostSubjectType.LIVE_GRAPH,
        subject_id=graph_id,
        total_amount=total,
        currency="USD",
        breakdown={},
        price_book_version="test",
        updated_at=datetime.now(UTC),
    )


async def test_a_graph_that_has_spent_its_budget_refuses_to_grow() -> None:
    """The cap D4 asks for, in the unit that actually matters. A count of extensions is a proxy —
    money is the thing, and since T8a the rollup can answer for a graph directly."""
    # Arrange
    compiler = ParkedCompiler()
    compiler.release.set()
    rollups = InMemorySubjectCostStore()
    service = LiveGraphService(
        compiler,  # type: ignore[arg-type]
        MemoryGraphStore(),
        subject_cost_store=rollups,
        throttle=LiveGraphThrottle(),
        graph_budget_usd=2.0,
    )
    graph = await service.compile(_TOPIC, run_id="r1", owner_id="alice")
    await rollups.upsert(cost=_rollup(graph.graph_id, total=2.5), owner_id="alice")

    # Act / Assert
    with pytest.raises(LiveWorkRefusedError):
        await service.extend(
            graph.graph_id,
            request="what about momentum?",
            anchors=[],
            run_id="r2",
            owner_id="alice",
        )

    # A map still inside its budget grows as before.
    await rollups.upsert(cost=_rollup(graph.graph_id, total=0.5), owner_id="alice")
    grown = await service.extend(
        graph.graph_id, request="what about momentum?", anchors=[], run_id="r3", owner_id="alice"
    )
    assert grown.version == graph.version + 1


class BrokenRollupStore:
    """A rollup store whose reads fail — a degraded ledger, which is a telemetry outage.

    It counts its reads so a test can say the extension was allowed *because the check ran and the
    store failed*, and not merely because nothing ever asked.
    """

    def __init__(self) -> None:
        self.reads = 0

    async def upsert(self, *, cost: SubjectCost, owner_id: str | None = None) -> None:
        raise PersistenceError("the rollup store is down")

    async def get(self, **kwargs: object) -> SubjectCost | None:
        self.reads += 1
        raise PersistenceError("the rollup store is down")

    async def delete_for_subject(self, **kwargs: object) -> int:
        raise PersistenceError("the rollup store is down")


async def test_a_broken_ledger_does_not_close_the_map() -> None:
    """Metering is observability. If a rollup read failing could refuse an extension, a telemetry
    outage would become a product outage — and the learner would be told they are out of budget
    when nobody knows what they have spent."""
    # Arrange
    compiler = ParkedCompiler()
    compiler.release.set()
    rollups = BrokenRollupStore()
    service = LiveGraphService(
        compiler,  # type: ignore[arg-type]
        MemoryGraphStore(),
        subject_cost_store=rollups,  # type: ignore[arg-type]
        throttle=LiveGraphThrottle(),
        graph_budget_usd=2.0,
    )
    graph = await service.compile(_TOPIC, run_id="r1", owner_id="alice")

    # Act
    grown = await service.extend(
        graph.graph_id, request="what about momentum?", anchors=[], run_id="r2", owner_id="alice"
    )

    # Assert — allowed, and allowed by the fail-open branch: the check has to have run and failed.
    # Without this second assertion a budget check deleted outright would pass here just as well.
    assert grown.version == graph.version + 1
    assert rollups.reads == 1, "the budget was never consulted, so nothing here proves fail-open"


async def test_the_app_wires_the_per_graph_budget(tmp_path: Path) -> None:
    """The money cap D4 asks for, proven where it actually ships.

    Everything else about the budget is pinned against a hand-built service, which cannot notice if
    the composition root stops passing ``graph_budget_usd`` — and that one dropped keyword would
    silently uncap every map in production while the whole suite stayed green.
    """
    # Arrange — a real ledger rollup, already past the configured cap for this graph.
    rollups = InMemorySubjectCostStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        live_graph_budget_usd=1.0,
    )
    app.dependency_overrides[get_subject_cost_store] = lambda: rollups
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        graph = (await client.post("/api/live/graphs", json={"topic": _TOPIC})).json()
        await rollups.upsert(cost=_rollup(graph["graphId"], total=1.5))

        # Act
        response = await client.post(
            f"/api/live/graphs/{graph['graphId']}/extend", json={"request": "what about momentum"}
        )

    # Assert
    assert response.status_code == 429, response.text
    assert "budget" in response.json()["detail"].lower()


async def test_an_unthrottled_service_is_unchanged() -> None:
    """The throttle is opt-in wiring, not a behaviour change: a service composed without one (the
    suites that predate this task, offline dev) compiles and extends exactly as before.

    Proven with *concurrent* compiles for one owner, because that is the only thing a default-limits
    throttle would refuse — sequential work stays well inside every default, so it could not tell
    "no throttle" apart from "a throttle nobody configured".
    """
    # Arrange
    compiler = ParkedCompiler()
    compiler.release.set()
    service = LiveGraphService(compiler, MemoryGraphStore())  # type: ignore[arg-type]

    # Act — three at once for the same owner; a wired throttle admits one (max_concurrent=1).
    graphs = await asyncio.gather(
        *(service.compile(_TOPIC, run_id=f"r{run}", owner_id="alice") for run in range(3))
    )

    # Assert
    assert len(graphs) == 3
    for run, graph in enumerate(graphs):
        await service.extend(
            graph.graph_id, request="more", anchors=[], run_id=f"e{run}", owner_id="alice"
        )
