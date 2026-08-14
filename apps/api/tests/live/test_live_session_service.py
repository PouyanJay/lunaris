"""The session plane below HTTP: what the service does with a learner's beliefs (Phase 2a, T4).

Nothing writes a belief through the API yet — the grader that does is T5 — so the claim that a
returning learner is met where they left off cannot be made through the endpoint. It is made here
instead, against the real stores and the real package, because the alternative is shipping the
knowledge read untested and discovering at T5 that the service was passing an empty model all along.

Owner scoping rides along rather than getting its own test here: the beliefs are stored under the
learner, so a service that read them unscoped would find an empty model and open at the root, which
is exactly what the first test would catch. The leak in the other direction — one learner reaching
another's map — is closed a layer earlier by the graph store, which refuses the read outright.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import pytest
from lunaris_api.live.session.service import LiveSessionService
from lunaris_api.live.session.turn_beat import TurnBeat
from lunaris_live.graph import ConceptGraph, MemoryGraphStore, StubGraphCompiler
from lunaris_live.session import (
    EvidenceKind,
    LearnerModel,
    MemoryKnowledgeStore,
    MemorySessionStore,
    Session,
    StubGrader,
    StubTutor,
    TutorUnavailableError,
    apply_evidence,
)
from lunaris_runtime.logging import configure_logging
from lunaris_runtime.persistence import PersistenceError

_TOPIC = "How neural networks learn"


async def _map() -> ConceptGraph:
    return await StubGraphCompiler().compile(_TOPIC, graph_id="g1", run_id="r0")


def _mastering(graph: ConceptGraph, node_id: str) -> LearnerModel:
    """Beliefs as the grader will write them (T5): repeated met evidence on one concept."""
    model = LearnerModel(graph_id=graph.graph_id)
    for turn in range(1, 4):
        model = apply_evidence(model, node_id, EvidenceKind.MET, at_turn=turn)
    return model


@pytest.fixture
async def wired() -> tuple[LiveSessionService, ConceptGraph, MemoryKnowledgeStore]:
    graph = await _map()
    graphs, knowledge = MemoryGraphStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    service = LiveSessionService(
        graphs,
        MemorySessionStore(),
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )
    return service, graph, knowledge


async def test_a_returning_learner_is_met_where_their_beliefs_left_them(
    wired: tuple[LiveSessionService, ConceptGraph, MemoryKnowledgeStore],
) -> None:
    # Arrange — they demonstrated the opening concept in an earlier session.
    service, graph, knowledge = wired
    knowledge.save(_mastering(graph, graph.topo_order[0]), owner_id="learner-1")

    # Act
    session = await service.start("g1", session_id="s1", owner_id="learner-1")

    # Assert — the next concept, not the one they already have.
    assert session.turns[0].move.node_id == graph.topo_order[1]


async def test_a_first_session_opens_at_the_start_of_the_map(
    wired: tuple[LiveSessionService, ConceptGraph, MemoryKnowledgeStore],
) -> None:
    """The other half of the same claim: with no beliefs stored, the director gets an empty model
    rather than a missing one, and the session opens where the map does."""
    # Arrange
    service, graph, _ = wired

    # Act
    session = await service.start("g1", session_id="s1", owner_id="learner-1")

    # Assert
    assert session.turns[0].move.node_id == graph.topo_order[0]


async def test_beliefs_stored_for_one_learner_are_not_read_for_another(
    wired: tuple[LiveSessionService, ConceptGraph, MemoryKnowledgeStore],
) -> None:
    """The knowledge read has to carry the owner through. Unscoped it would return an empty model
    here — harmless — but on a store where a stranger's row *could* match it would walk somebody
    past concepts they have never met, and it would look like the product working."""
    # Arrange — the beliefs belong to another learner entirely.
    service, graph, knowledge = wired
    knowledge.save(_mastering(graph, graph.topo_order[0]), owner_id="someone-else")

    # Act
    session = await service.start("g1", session_id="s2", owner_id="learner-1")

    # Assert
    assert session.turns[0].move.node_id == graph.topo_order[0]


async def test_the_transcript_is_written_before_the_belief() -> None:
    """Two writes, not one transaction, so the order is chosen for how each half fails.

    Transcript first means a crash between them under-counts evidence: the learner sees a graded
    turn whose belief did not move, and the concept comes round again. The other order looks safer
    and is not — the response is a retryable 503, a retry re-grades the same answer against a
    transcript that never recorded it, and one lucky guess plus a storage blip clears the mastery
    bar that ``_PULL`` was sized to keep two answers away.
    """
    # Arrange — a session store that reads back fine and refuses every write.
    graph = await _map()
    graphs, knowledge = MemoryGraphStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    opened = await LiveSessionService(
        graphs,
        MemorySessionStore(),
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    ).start("g1", session_id="s1", owner_id="learner-1")

    class RefusesToWrite:
        def save(
            self,
            session: Session,
            *,
            owner_id: str | None = None,
            expect_turns: int | None = None,
        ) -> None:
            raise PersistenceError("storage is having trouble")

        def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
            return opened

    service = LiveSessionService(
        graphs,
        RefusesToWrite(),
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )

    # Act
    with pytest.raises(PersistenceError):
        await service.answer("s1", "I have no idea.", answering_seq=1, owner_id="learner-1")

    # Assert — the belief never landed, because the transcript never did.
    assert knowledge.load("g1", owner_id="learner-1").nodes == {}


async def test_a_clock_that_stepped_backwards_does_not_break_a_turn() -> None:
    """Hosts correct their clocks. If the machine answering a turn has stepped behind the one that
    opened the session, the elapsed time is negative — and ``SessionClock.elapsed_s`` is ``ge=0``,
    so the turn would fail on a validation error no handler translates and the learner would get a
    bare 500 for something entirely on our side."""
    # Arrange — a session stamped in the future, which is what a backward step looks like.
    graph = await _map()
    graphs, sessions, knowledge = MemoryGraphStore(), MemorySessionStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )
    opened = await service.start("g1", session_id="s1", owner_id="learner-1")
    sessions.save(
        opened.model_copy(update={"started_at": datetime.now(UTC) + timedelta(minutes=5)}),
        owner_id="learner-1",
    )

    # Act
    answered = await service.answer("s1", "An answer.", answering_seq=1, owner_id="learner-1")

    # Assert — the turn happened, treated as no time having passed.
    assert answered.turns[0].answer == "An answer."


async def test_no_fragment_is_lost_when_the_turn_finishes_before_anyone_reads_it() -> None:
    """The stream's tail, in the worst case for it (Phase 2b, T2).

    The turn here is **already finished** before the relay reads a single fragment, which is the
    shape that would lose the end of a lesson if the loop ever stopped consuming once the task was
    done. A learner would then read a lesson that stops mid-word while the stored session holds all
    of it — the one disagreement between the stream and the row this transport must not produce.

    Driven against the relay directly rather than through ``stream_answer``, because every path
    through it awaits a store write after the last fragment and so never presents this ordering.
    Naming that is the point: the guarantee is a property of the loop, not of how fast the tutor
    happens to be.
    """
    # Arrange — a turn that is already finished, with everything it said still in the queue.
    graph = await _map()
    graphs, sessions, knowledge = MemoryGraphStore(), MemorySessionStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )
    opened = await service.start("g1", session_id="s1", owner_id="learner-1")

    queue: asyncio.Queue[str] = asyncio.Queue()

    async def instant_turn() -> Session:
        queue.put_nowait("Every word ")
        queue.put_nowait("of it.")
        return opened

    taking = asyncio.create_task(instant_turn())
    await taking

    # Act
    beats = [beat async for beat in service._beats(taking, queue, run_id="r1", session_id="s1")]

    # Assert — both fragments, then the session, in that order.
    assert beats == [("delta", "Every word "), ("delta", "of it."), ("session", opened)]


async def test_a_learner_who_walks_away_mid_turn_still_gets_the_turn_they_paid_for() -> None:
    """A dropped stream must not cancel the turn behind it (Phase 2b, T2).

    By the time a connection drops, the turn has already paid a grader and a tutor. Cancelling it
    would bill somebody for a lesson nobody can get back — so it runs on, persists, and re-reading
    over ``GET /{id}`` is a free recovery. Phase 1 settled this shape for the compile stream, and it
    binds harder here because a compile can at least be re-run.

    Driven against the service rather than the ASGI app deliberately: ``ASGITransport`` runs a
    response generator to completion whether or not the client keeps reading, so it cannot express a
    learner walking away.
    """

    # Arrange — a tutor slow enough that the stream can be abandoned mid-lesson.
    class SlowTutor(StubTutor):
        async def stream(self, move, node, **kwargs: object) -> AsyncIterator[str]:  # type: ignore[override]
            yield "The first half. "
            await asyncio.sleep(0.02)
            yield "The second half."

    graph = await _map()
    graphs, sessions, knowledge = MemoryGraphStore(), MemorySessionStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=SlowTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )
    opened = await service.start("g1", session_id="s1", owner_id="learner-1")

    # Act — read one fragment, then walk away, as a closed connection does.
    stream = await service.stream_answer("s1", "An answer.", run_id="r1", owner_id="learner-1")
    assert await anext(stream) == (TurnBeat.DELTA, "The first half. ")
    await stream.aclose()

    # Assert — the turn landed behind the departed learner.
    for _ in range(100):
        stored = sessions.load("s1", owner_id="learner-1")
        if len(stored.turns) > len(opened.turns):
            break
        await asyncio.sleep(0.01)
    else:  # pragma: no cover - only reached if the detached turn never lands
        pytest.fail("the turn was cancelled when the stream went away")
    assert stored.turns[0].answer == "An answer."
    assert stored.turns[-1].tutor == "The first half. The second half."


async def test_a_turn_that_fails_after_its_learner_left_is_still_traceable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The one failure nobody is watching, so the log is the only thing that can report it.

    Correlation cannot ride contextvars here: the turn runs in its own task, which snapshots the
    context at creation, so a binding made inside it never reaches a done-callback running back in
    the caller's context. The ids are passed by hand for exactly that reason — and a warning naming
    a failure with no run to attach it to is barely a warning at all.
    """
    # Arrange — a tutor that dies after the learner has already gone.
    #
    # Logging is configured here rather than inherited: every other test in this file drives the
    # service directly, so nothing has built the app that normally configures structlog, and the
    # default console renderer emits no JSON to read. The sibling compile-stream file gets away
    # without this only because one of its own tests happens to build an app first — an ordering
    # dependency, not a guarantee.
    configure_logging()

    class FailsAfterTheFirstFragment(StubTutor):
        async def stream(self, move, node, **kwargs: object) -> AsyncIterator[str]:  # type: ignore[override]
            yield "The first half. "
            await asyncio.sleep(0.01)
            raise TutorUnavailableError("the model gave up after the learner did")

    graph = await _map()
    graphs, sessions, knowledge = MemoryGraphStore(), MemorySessionStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=FailsAfterTheFirstFragment(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )
    await service.start("g1", session_id="s-lost", owner_id="learner-1")
    capsys.readouterr()  # discard the opening's own lines

    # Act — one fragment, then walk away; the turn fails behind the departed learner.
    stream = await service.stream_answer(
        "s-lost", "An answer.", run_id="run-lost", owner_id="learner-1"
    )
    await anext(stream)
    await stream.aclose()
    await asyncio.sleep(0.05)

    # Assert — the failure is on the record, and it names the run and the session it belongs to.
    failures = [
        line
        for line in _json_log_lines(capsys)
        if line.get("event") == "live.session.detached_turn_failed"
    ]
    assert failures, "a turn failed after its stream detached and said nothing"
    assert failures[-1]["run_id"] == "run-lost"
    assert failures[-1]["session_id"] == "s-lost"


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]


async def test_a_cancelled_reader_leaves_no_task_parked_on_the_queue() -> None:
    """The other way a stream ends, and the only one that can leak (Phase 2b, T2).

    ``aclose()`` throws at the ``yield``, where the relay's pending ``queue.get()`` has *already*
    been consumed — so it cannot show this. A cancelled reader can: ASGI cancels the response task,
    the cancellation lands inside ``asyncio.wait``, and the ``queue.get()`` future is an
    **independent** task that a cancelled parent does not take with it. Left parked on the queue it
    is a task nobody will ever await, collected later while still pending — a "Task was destroyed
    but it is pending!" with nothing to trace it back to.

    The turn itself is the one thing that should still be running afterwards: it is deliberately not
    cancelled, because it has already paid for itself.
    """

    # Arrange — a tutor slow enough that the reader can be cancelled between two fragments.
    class SlowTutor(StubTutor):
        async def stream(self, move, node, **kwargs: object) -> AsyncIterator[str]:  # type: ignore[override]
            yield "The first half. "
            await asyncio.sleep(0.2)
            yield "The second half."

    graph = await _map()
    graphs, sessions, knowledge = MemoryGraphStore(), MemorySessionStore(), MemoryKnowledgeStore()
    graphs.save(graph, owner_id="learner-1")
    service = LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=SlowTutor(),
        grader=StubGrader(),
        session_budget_s=1800.0,
    )
    await service.start("g1", session_id="s1", owner_id="learner-1")
    stream = await service.stream_answer("s1", "An answer.", run_id="r1", owner_id="learner-1")

    read: list[tuple[TurnBeat, object]] = []

    async def reader() -> None:
        async for beat in stream:
            read.append(beat)

    # Act — read the first fragment, then cancel while the relay waits for the second.
    consumer = asyncio.create_task(reader())
    for _ in range(200):
        if read:
            break
        await asyncio.sleep(0.005)
    assert read, "the relay never produced a fragment, so nothing was cancelled mid-wait"
    consumer.cancel()
    with suppress(asyncio.CancelledError):
        await consumer

    # Assert — exactly one thing still running, and it is the turn.
    left = {
        task
        for task in asyncio.all_tasks()
        if not task.done() and task is not asyncio.current_task()
    }
    assert len(left) == 1, (
        f"the relay left something parked: {sorted(t.get_coro().__qualname__ for t in left)}"
    )
    assert "_take_and_save" in next(iter(left)).get_coro().__qualname__, (
        "the turn is the one thing that should outlive its reader"
    )
