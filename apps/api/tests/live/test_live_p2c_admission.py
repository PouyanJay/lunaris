"""Lunaris Live, Phase 2c — admission and metering over the placement and prefetch paths (T8).

Plan §3.6: no new cost subject. Interview turns, the mapper, the prefetch and the recap are all the
session's money under ``LIVE_SESSION``, and the $2 ceiling binds them all; a topic-open consumes a
compile slot AND a session opening; the interview is bounded by a configured number of questions.
What this pins, through the real app: a placing session past its ceiling is not interviewed
further (both transports share the door); the root's material is not prefetched for a session past
its ceiling; a topic-open the compile plane refuses does not spend the day's opening; the interview
asks as many questions as configured, and the compile grace is a setting.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from _live_stack import GatedCompiler, agui_answer, settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.dependencies import get_cost_event_store, get_subject_cost_store
from lunaris_api.live.dependencies import (
    get_live_graph_service,
    launched_compiles,
    resolve_graph_store,
)
from lunaris_api.live.graph_throttle import LiveGraphThrottle
from lunaris_api.live.launched_compiles import LaunchedCompiles
from lunaris_api.live.service import LiveGraphService
from lunaris_api.live.session.dependencies import get_live_tutor
from lunaris_api.live.session.prefetch_registry import prefetch_registry
from lunaris_live.graph import ConceptNode, MasteryCriterion
from lunaris_live.session import DirectorMove, LessonParts, StubTutor, WorkedExample
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.schema import CostSubjectType, SubjectCost


class CountingIllustrator(StubTutor):
    """The stub tutor, counting what it was asked to illustrate."""

    def __init__(self) -> None:
        self.illustrated: list[str] = []

    async def illustrate(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None = None,
        already_said: Sequence[str] = (),
        profile: str | None = None,
        run_id: str,
    ) -> LessonParts:
        self.illustrated.append(node.id)
        return LessonParts(
            worked_example=WorkedExample(title=f"{node.name}, worked", steps=["one", "two"]),
            hint=f"About {node.name}.",
            practice=[f"Try {node.name}."],
        )


async def _past_the_ceiling(
    rollup: InMemorySubjectCostStore, session_id: str, *, spent: float = 5.0
) -> None:
    await rollup.upsert(
        cost=SubjectCost(
            subject_type=CostSubjectType.LIVE_SESSION,
            subject_id=session_id,
            total_amount=spent,
            currency="USD",
            breakdown={},
            price_book_version="test",
            updated_at=datetime.now(UTC),
        ),
        owner_id=None,
    )


@pytest.fixture
async def stack(
    tmp_path: Path,
) -> AsyncIterator[
    tuple[httpx.AsyncClient, GatedCompiler, CountingIllustrator, InMemorySubjectCostStore]
]:
    """The app over a held compile, a counting tutor, a real ledger and a $0.01 ceiling."""
    settings = settings_for(tmp_path, live_session_budget_usd=0.01)
    compiler, tutor = GatedCompiler(), CountingIllustrator()
    events, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    # Over the process-wide launch registry, so the test can meet the compile at its end.
    app.dependency_overrides[get_live_graph_service] = lambda: LiveGraphService(
        compiler, resolve_graph_store(settings), launched=launched_compiles()
    )
    app.dependency_overrides[get_live_tutor] = lambda: tutor
    app.dependency_overrides[get_cost_event_store] = lambda: events
    app.dependency_overrides[get_subject_cost_store] = lambda: rollup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, compiler, tutor, rollup
        compiler.release.set()
        await prefetch_registry().settled()


async def test_a_placing_session_past_its_ceiling_is_not_interviewed_further(
    stack: tuple[httpx.AsyncClient, GatedCompiler, CountingIllustrator, InMemorySubjectCostStore],
) -> None:
    """The interview is the session's money (§3.6): a placing session whose ledger is past the
    ceiling is refused its next question, on both transports, in the same words."""
    client, compiler, _, rollup = stack
    session = (await client.post("/api/live/sessions", json={"topic": "Tides"})).json()
    await asyncio.wait_for(compiler.entered.wait(), 5)
    await _past_the_ceiling(rollup, session["sessionId"])
    url = f"/api/live/sessions/{session['sessionId']}"

    over_rest = await client.post(f"{url}/turns", json={"answer": "A bit.", "answeringSeq": 1})
    over_agui = await client.post(f"{url}/agui", json=agui_answer("A bit."))

    assert over_rest.status_code == 429, over_rest.text
    assert "cost ceiling" in over_rest.json()["detail"]
    assert over_agui.status_code == 429, over_agui.text
    assert over_agui.json()["detail"] == over_rest.json()["detail"]


async def test_the_ceiling_binds_at_the_ceiling_not_a_cent_past_it(
    stack: tuple[httpx.AsyncClient, GatedCompiler, CountingIllustrator, InMemorySubjectCostStore],
) -> None:
    """A session that has spent exactly its ceiling has spent its ceiling: the next turn is
    refused. Pinned because every other ceiling test plants a spend far past the line, where a
    ``>`` and a ``>=`` are the same test."""
    client, compiler, _, rollup = stack
    session = (await client.post("/api/live/sessions", json={"topic": "Tides"})).json()
    await asyncio.wait_for(compiler.entered.wait(), 5)
    await _past_the_ceiling(rollup, session["sessionId"], spent=0.01)

    response = await client.post(
        f"/api/live/sessions/{session['sessionId']}/turns",
        json={"answer": "A bit.", "answeringSeq": 1},
    )

    assert response.status_code == 429, response.text


async def test_the_roots_material_is_not_prefetched_for_a_session_past_its_ceiling(
    stack: tuple[httpx.AsyncClient, GatedCompiler, CountingIllustrator, InMemorySubjectCostStore],
) -> None:
    """The prefetch is the session's money too, and it runs when nobody is asking for a turn: the
    map lands, the root's material would be asked for — and is not, because the ledger says the
    session has spent its ceiling. Nothing awaits a prefetch, so the ceiling has to be read by the
    prefetch itself, not by the turn that scheduled it (T4 left this to T8)."""
    client, compiler, tutor, rollup = stack
    session = (await client.post("/api/live/sessions", json={"topic": "Tides"})).json()
    await asyncio.wait_for(compiler.entered.wait(), 5)
    await _past_the_ceiling(rollup, session["sessionId"])

    compiler.release.set()
    compiling = launched_compiles().compiling(session["graphId"])
    assert compiling is not None
    await compiling
    await prefetch_registry().settled()

    assert tutor.illustrated == [], "the root's material was refused, not asked for"


async def test_a_topic_open_the_compile_plane_refuses_does_not_spend_the_opening(
    tmp_path: Path,
) -> None:
    """A topic-open consumes a compile slot AND a session opening (§3.6), and it must consume both
    or neither: T1 counted the opening before the compile's own admission ran, so a learner whose
    compile was refused (one already building) had also spent an opening on nothing. With two
    openings a day and one compile at a time: a held compile, a refused second topic, and the
    second opening still there for a map."""
    settings = settings_for(tmp_path, live_session_daily_cap=2, live_compile_max_concurrent=1)
    compiler = GatedCompiler(held_topic="Held")
    # One compile plane, so its throttle sees every request (a per-request throttle counts none).
    compiles = LiveGraphService(
        compiler,
        resolve_graph_store(settings),
        throttle=LiveGraphThrottle(
            compile_daily_cap=20, compile_max_concurrent=1, extend_daily_cap=50
        ),
        launched=LaunchedCompiles(),
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_graph_service] = lambda: compiles
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            graph = (await client.post("/api/live/graphs", json={"topic": "Tides"})).json()
            held = await client.post("/api/live/sessions", json={"topic": "Held"})
            assert held.status_code == 201, held.text
            await asyncio.wait_for(compiler.entered.wait(), 5)

            refused = await client.post("/api/live/sessions", json={"topic": "Another"})
            assert refused.status_code == 429, refused.text
            assert "already being built" in refused.json()["detail"]

            on_a_map = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
            assert on_a_map.status_code == 201, on_a_map.text
            # And the allowance is exactly two: a third opening is the day's cap, said as such.
            third = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
            assert third.status_code == 429, third.text
            assert "already being built" not in third.json()["detail"]
    finally:
        compiler.release.set()


async def test_the_interview_asks_as_many_questions_as_configured(tmp_path: Path) -> None:
    """``live_interview_max_questions`` is a setting (T2 left it a constant): with one question
    allowed, the first answer ends the interview and, the map still held, the session warms."""
    settings = settings_for(tmp_path, live_interview_max_questions=1)
    compiler = GatedCompiler()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_graph_service] = lambda: LiveGraphService(
        compiler, resolve_graph_store(settings)
    )
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            session = (await client.post("/api/live/sessions", json={"topic": "Tides"})).json()
            await asyncio.wait_for(compiler.entered.wait(), 5)

            response = await client.post(
                f"/api/live/sessions/{session['sessionId']}/turns",
                json={"answer": "A bit.", "answeringSeq": 1},
            )

            assert response.status_code == 200, response.text
            assert response.json()["status"] == "warming"
    finally:
        compiler.release.set()


def test_the_container_hands_the_session_plane_its_interview_and_gracesettings_for(
    tmp_path: Path,
) -> None:
    """Proves the wiring, not the parts (the sim-socket suite's lesson): every other test here
    composes the service by hand, so a setting the container forgot to pass would leave them all
    green. The container is run with the settings turned to values nothing else uses, and the
    service is asked what it was handed."""
    from lunaris_api.live.dependencies import get_live_graph_service as graph_service_of
    from lunaris_api.live.session.dependencies import (
        get_live_grader,
        get_live_interviewer,
        get_live_prior_mapper,
        get_live_session_service,
        get_live_sims,
    )

    settings = settings_for(tmp_path, live_interview_max_questions=7, live_compile_grace_s=1.5)

    service = get_live_session_service(
        settings=settings,
        tutor=get_live_tutor(settings),
        grader=get_live_grader(settings),
        sims=get_live_sims(settings),
        interviewer=get_live_interviewer(settings),
        mapper=get_live_prior_mapper(settings),
        compiles=graph_service_of(settings, cost_event_store=None, subject_cost_store=None),
        cost_event_store=None,
        subject_cost_store=None,
    )

    # White-box, like the sim-socket suite's own wiring test (``service._sims``): a class's public
    # surface serves its callers, not its test.
    assert service._interview_max_questions == 7
    assert service._compile_grace_s == 1.5
