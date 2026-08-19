"""The compile as a stream — what the learner watches for the three minutes it takes.

The await-full ``POST /api/live/graphs`` stays the durable entry point, but it can only ever say
"working on it" for the whole compile. This is the surface that can say more: the compiler counts
its concepts, the service relays them, and the learner sees a map being built rather than a spinner.

Exercised through the real ASGI app over httpx — the stub compiler stands in for the model, but the
router, the service and the store are the production ones.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_live.graph import ConceptGraph, GraphCompilationError
from lunaris_runtime.logging import configure_logging


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _frames(
    client: httpx.AsyncClient, topic: str
) -> tuple[list[tuple[str, Any]], httpx.Headers]:
    """Every ``(event, data)`` frame of one compile stream, plus the response headers."""
    collected: list[tuple[str, Any]] = []
    async with client.stream("GET", "/api/live/graphs/stream", params={"topic": topic}) as response:
        assert response.status_code == 200, await response.aread()
        headers = response.headers
        event = ""
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                collected.append((event, json.loads(line.removeprefix("data:").strip())))
    return collected, headers


async def test_the_stream_reports_progress_and_ends_with_the_finished_map(
    client: httpx.AsyncClient,
) -> None:
    # Act
    frames, headers = await _frames(client, "How neural networks learn")

    # Assert — an event stream, not a JSON response that happens to arrive late.
    assert headers["content-type"].startswith("text/event-stream")

    kinds = [kind for kind, _ in frames]
    assert "progress" in kinds, "the stream said nothing until it was finished"
    assert kinds[-1] == "graph", "the stream ended without handing over the map"

    graph = frames[-1][1]
    assert graph["topic"] == "How neural networks learn"
    assert graph["isAcyclic"] is True
    assert len(graph["nodes"]) >= 2


async def test_progress_counts_the_concepts_the_learner_is_waiting_on(
    client: httpx.AsyncClient,
) -> None:
    """The point of the stream. A phase alone is a spinner with a label; a count is a bar."""
    # Act
    frames, _ = await _frames(client, "Tides")

    # Assert
    progress = [data for kind, data in frames if kind == "progress"]
    assert progress[0]["phase"] == "decomposing"
    authoring = [event for event in progress if event["phase"] == "authoring"]
    assert authoring, "no countable phase was ever reported"
    assert authoring[-1]["done"] == authoring[-1]["total"] > 0
    # camelCase on the wire like every other Live contract — the web reads these keys directly.
    assert set(progress[0]) == {"phase", "done", "total"}


async def test_a_streamed_graph_is_persisted_like_a_posted_one(client: httpx.AsyncClient) -> None:
    """The stream is an entry point, not a preview: what it hands over is durable and re-readable,
    or a learner who refreshes has lost the three minutes they just spent."""
    # Arrange
    frames, _ = await _frames(client, "Photosynthesis")
    streamed = frames[-1][1]

    # Act
    response = await client.get(f"/api/live/graphs/{streamed['graphId']}")

    # Assert
    assert response.status_code == 200, response.text
    assert response.json() == streamed


async def test_the_stream_is_correlated_by_a_run_id_sent_before_the_body(
    client: httpx.AsyncClient,
) -> None:
    """The header has to be on the response, not in a frame: once the body starts, a client whose
    stream drops has no other way to name the run it lost."""
    # Act
    _, headers = await _frames(client, "Tides")

    # Assert
    assert headers["X-Run-Id"]


async def test_a_failed_compile_ends_in_an_error_frame_rather_than_a_silent_close(
    tmp_path: Path,
) -> None:
    """A stream cannot answer 502 — its status was sent before the failure happened. So the failure
    has to be a frame, or the web sees a body that simply stops and cannot tell a broken compile
    from a dropped connection: one is worth retrying, the other worth re-attaching to.
    """
    # Arrange — a compiler that fails the way a real one does when decomposition returns junk.
    from lunaris_api.live.dependencies import get_live_graph_service
    from lunaris_api.live.service import LiveGraphService
    from lunaris_live.graph import GraphCompilationError, MemoryGraphStore

    class FailingCompiler:
        async def compile(self, topic: str, **kwargs: object) -> ConceptGraph:
            raise GraphCompilationError(f"could not decompose {topic!r} into concepts")

        async def extend(self, *args: object, **kwargs: object) -> ConceptGraph:
            raise NotImplementedError

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    app.dependency_overrides[get_live_graph_service] = lambda: LiveGraphService(
        FailingCompiler(), MemoryGraphStore()
    )

    # Act
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        frames, _ = await _frames(http_client, "asdfgh")

    # Assert — the last word is an honest, actionable failure rather than nothing at all, and it is
    # word-for-word what the await-full path answers with. Pinned by value rather than by keyword:
    # the two entry points share their copy through one constant, and the whole point of sharing it
    # is that one learner's failure cannot come to read differently from another's.
    kind, data = frames[-1]
    assert kind == "error"
    assert data["message"] == "Couldn't map this topic. Try again, or rephrase it."
    assert data["runId"], "a failed compile is exactly when the run id has to be recoverable"


async def test_a_learner_who_leaves_mid_compile_still_gets_a_map_they_can_come_back_to(
    tmp_path: Path,
) -> None:
    """The re-attach promise the ``X-Graph-Id`` header makes, exercised at the service.

    A dropped stream must not cancel minutes of work: the compile finishes, persists, and the id the
    caller already holds resolves. Driven through the service rather than the router because what is
    under test is abandoning the generator, which is exactly what a disconnect does.
    """
    # Arrange — a compiler that reports early and finishes late, so the stream is genuinely
    # abandoned *mid*-compile. With the instant stub the compile would already be over by the first
    # frame, and the test would pass even if a disconnect cancelled the work outright.
    from lunaris_api.live.service import LiveGraphService
    from lunaris_live.graph import CompilePhase, ConceptNode, MemoryGraphStore
    from lunaris_live.graph.report_progress import report_progress

    class SlowCompiler:
        async def compile(
            self, topic: str, *, graph_id: str, run_id: str, **kwargs: object
        ) -> ConceptGraph:
            sink = kwargs.get("on_progress")
            report_progress(sink, CompilePhase.DECOMPOSING)  # type: ignore[arg-type]
            await asyncio.sleep(0.05)  # the minutes a real compile spends, in miniature
            report_progress(sink, CompilePhase.ASSEMBLING, done=1, total=1)  # type: ignore[arg-type]
            return ConceptGraph(
                graph_id=graph_id,
                topic=topic,
                nodes=[ConceptNode(id="a", name="A", definition="A concept.")],
                topo_order=["a"],
                is_acyclic=True,
            )

        async def extend(self, *args: object, **kwargs: object) -> ConceptGraph:
            raise NotImplementedError

    store = MemoryGraphStore()
    service = LiveGraphService(SlowCompiler(), store)

    # Act — take the first frame, then walk away, as a closed connection does.
    stream = service.stream("Tides", graph_id="g-detached", run_id="r1")
    await anext(stream)
    await stream.aclose()

    # Assert — the compile ran on behind the departed learner and persisted, so the id handed over
    # in the header before the body still resolves.
    for _ in range(100):
        try:
            graph = store.load("g-detached", owner_id=None)
            break
        except FileNotFoundError:
            await asyncio.sleep(0.01)
    else:  # pragma: no cover - only reached if the detached compile never lands
        pytest.fail("the compile was cancelled when the stream went away")
    assert graph.topic == "Tides"


async def test_a_compile_that_fails_after_its_learner_left_is_still_traceable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The one failure nobody is watching, so the log is the only thing that can report it.

    Correlation cannot ride contextvars here: the compile runs in its own task, which snapshots the
    context at creation, so the binding made inside it never reaches a done-callback running back in
    the caller's context. Ids passed by hand are the only thing that works — and a warning naming a
    failure with no run to attach it to is barely a warning at all.

    Driven through the service rather than the ASGI app deliberately: ``ASGITransport`` runs the
    response generator to completion whether or not the client keeps reading, so it cannot express a
    learner walking away mid-compile.
    """
    # Arrange
    from lunaris_api.live.service import LiveGraphService
    from lunaris_live.graph import CompilePhase, MemoryGraphStore
    from lunaris_live.graph.report_progress import report_progress

    class FailsAfterTheFirstBeat:
        async def compile(
            self, topic: str, *, graph_id: str, run_id: str, **kwargs: object
        ) -> ConceptGraph:
            report_progress(kwargs.get("on_progress"), CompilePhase.DECOMPOSING)  # type: ignore[arg-type]
            await asyncio.sleep(0.01)
            raise GraphCompilationError("the model gave up after the learner did")

        async def extend(self, *args: object, **kwargs: object) -> ConceptGraph:
            raise NotImplementedError

    configure_logging(json_output=True)
    service = LiveGraphService(FailsAfterTheFirstBeat(), MemoryGraphStore())

    # Act — one frame, then walk away; the compile fails behind the departed learner. Meeting the
    # compile at its end (rather than sleeping past it) is what makes this deterministic: the
    # service keeps no handle to the task, so it is found among the loop's.
    stream = service.stream("Tides", graph_id="g-lost", run_id="run-lost")
    await anext(stream)
    await stream.aclose()
    (compiling,) = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    with pytest.raises(GraphCompilationError):
        await compiling

    # Assert — the failure is on the record, and it names the run and the map it belongs to.
    failures = [
        line
        for line in _json_log_lines(capsys)
        if line.get("event") == "live.graph.detached_compile_failed"
    ]
    assert failures, "a compile failed after its stream detached and said nothing"
    assert failures[-1]["run_id"] == "run-lost"
    assert failures[-1]["graph_id"] == "g-lost"


async def test_a_launched_compile_that_fails_is_on_the_record_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """P2c T1: a session opened on a topic launches its compile and walks away from it at once —
    there is no stream to detach from, so ``launch`` has to absorb the task's result itself. A
    compile that failed behind a placing session and said nothing would be exactly the failure a
    learner reports as "it never started teaching", with no line for anyone to find.

    Found by mutation: deleting the absorb from ``launch`` left every T1 test green.
    """
    # Arrange
    from lunaris_api.live.service import LiveGraphService
    from lunaris_live.graph import MemoryGraphStore

    class Fails:
        async def compile(
            self, topic: str, *, graph_id: str, run_id: str, **_: object
        ) -> ConceptGraph:
            await asyncio.sleep(0.01)
            raise GraphCompilationError("the model gave up while the learner was being interviewed")

        async def extend(self, *args: object, **kwargs: object) -> ConceptGraph:
            raise NotImplementedError

    # Driven without ``create_app``, so the JSON logging that call configures is configured here:
    # otherwise this test passes only when a ``client``-using test ran before it (found in review).
    configure_logging(json_output=True)
    service = LiveGraphService(Fails(), MemoryGraphStore())

    # Act — launch and walk away, as the placement path does; then meet the task at its end. The
    # await IS the rendezvous: no sleep, no guess about how long the fake compile takes.
    task = service.launch("Tides", graph_id="g-placing", run_id="run-placing")
    with pytest.raises(GraphCompilationError):
        await task

    # Assert — the failure is on the record, and it names the run and the map it belongs to. (The
    # done-callback ran before the await returned, because callbacks are scheduled on completion
    # and the awaiting task resumes after them.)
    failures = [
        line
        for line in _json_log_lines(capsys)
        if line.get("event") == "live.graph.detached_compile_failed"
    ]
    assert failures, "a launched compile failed and said nothing"
    assert failures[-1]["run_id"] == "run-placing"
    assert failures[-1]["graph_id"] == "g-placing"


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]


@pytest.mark.parametrize("topic", ["", "   ", "x" * 201])
async def test_an_unusable_topic_is_rejected_before_the_stream_opens(
    client: httpx.AsyncClient, topic: str
) -> None:
    """Validated at the edge while a real status code is still available to send.

    The all-whitespace case is the one ``min_length`` alone lets through, and it is the expensive
    one: it would compile a map of nothing and bill a learner for the model calls.
    """
    response = await client.get("/api/live/graphs/stream", params={"topic": topic})

    assert response.status_code == 422
