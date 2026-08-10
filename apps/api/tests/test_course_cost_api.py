"""Walking-skeleton integration tests for per-course cost metering (course-cost-metering, T1).

They traverse the real layers end-to-end: a build records a cost event through the
``CostEventRecorder`` into the append-only ledger, the recorder rolls it up into ``course_costs``,
and the owner reads the total back over HTTP at ``GET /api/courses/{id}/cost`` — with an in-memory
store pair standing in for Supabase (no live DB in CI). Real metering of each provider comes in
later tasks; here the event is a stub, proving only that the write -> rollup -> read path is wired.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.dependencies import get_cost_event_store, get_subject_cost_store
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.metering import CostEventRecorder
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.schema import CostPocket, CostProvider, CostSubjectType

_COURSE_ID = "course-skeleton"
_RUN_ID = "run-skeleton"
_PRICE_BOOK_VERSION = "v0-skeleton"


@pytest.fixture
def event_store() -> InMemoryCostEventStore:
    return InMemoryCostEventStore()


@pytest.fixture
def subject_cost_store() -> InMemorySubjectCostStore:
    return InMemorySubjectCostStore()


@pytest.fixture
async def http_with(
    subject_cost_store: InMemorySubjectCostStore,
    event_store: InMemoryCostEventStore,
) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    # The cost endpoints read the rollup store (the total) and the ledger store (the drill-through);
    # override both so the test's recorder and the endpoints share one instance each (auth off → the
    # unscoped single-user path, owner_id is None).
    app.dependency_overrides[get_subject_cost_store] = lambda: subject_cost_store
    app.dependency_overrides[get_cost_event_store] = lambda: event_store
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_recorded_cost_rolls_up_and_reads_back_over_http(
    http_with: httpx.AsyncClient,
    event_store: InMemoryCostEventStore,
    subject_cost_store: InMemorySubjectCostStore,
) -> None:
    # Arrange — a build records one (stub) metered call, then finalizes to roll the course up.
    recorder = CostEventRecorder(
        event_store,
        subject_cost_store,
        run_id=_RUN_ID,
        subject_type=CostSubjectType.COURSE,
        subject_id=_COURSE_ID,
        price_book_version=_PRICE_BOOK_VERSION,
    )
    await recorder.record(
        component="walking_skeleton",
        provider=CostProvider.LOCAL,
        model=None,
        usage={"stub": 1},
        amount=0.5,
        pocket=CostPocket.PLATFORM,
    )
    await recorder.finalize()

    # Act — the owner reads the course's cost over the real HTTP path.
    response = await http_with.get(f"/api/courses/{_COURSE_ID}/cost")

    # Assert — the rollup traversed recorder → ledger → rollup store → API with the total intact.
    assert response.status_code == 200
    body = response.json()
    assert body is not None, "expected a metered rollup, not a null (not-metered) body"
    # The rollup names what it was spent on, not just how much: a course id and a graph id can
    # collide, so the type is what keeps one product's spend out of the other's total.
    assert body["subjectType"] == "course"
    assert body["subjectId"] == _COURSE_ID
    assert body["totalAmount"] == pytest.approx(0.5)
    assert body["currency"] == "USD"
    assert body["priceBookVersion"] == _PRICE_BOOK_VERSION
    # The drill-through breakdown the Overview reads: per-component / per-provider / per-pocket.
    breakdown = body["breakdown"]
    assert breakdown["eventCount"] == 1
    assert breakdown["byComponent"]["walking_skeleton"] == pytest.approx(0.5)
    assert breakdown["byProvider"]["local"] == pytest.approx(0.5)
    assert breakdown["byPocket"]["platform"] == pytest.approx(0.5)

    # Behavioral: the append-only ledger holds the underlying event (the drill-through source).
    ledger = await event_store.list_for_subject(
        subject_type=CostSubjectType.COURSE,
        subject_id=_COURSE_ID,
    )
    assert [e.seq for e in ledger] == [0]
    assert ledger[0].component == "walking_skeleton"


async def test_unmetered_course_reads_as_null_not_404(http_with: httpx.AsyncClient) -> None:
    # Act — a course that was never metered (pre-feature, still building, or unknown).
    response = await http_with.get("/api/courses/never-metered/cost")

    # Assert — a 200 null, not a 404: the web renders a "not metered" state, not an error.
    assert response.status_code == 200
    assert response.json() is None


async def test_cost_ledger_reads_back_over_http_for_the_drill_through(
    http_with: httpx.AsyncClient,
    event_store: InMemoryCostEventStore,
    subject_cost_store: InMemorySubjectCostStore,
) -> None:
    # Arrange — a build records two metered calls across two providers, ordered by emission.
    recorder = CostEventRecorder(
        event_store,
        subject_cost_store,
        run_id=_RUN_ID,
        subject_type=CostSubjectType.COURSE,
        subject_id=_COURSE_ID,
        price_book_version=_PRICE_BOOK_VERSION,
    )
    await recorder.record(
        component="planner",
        provider=CostProvider.ANTHROPIC,
        model="claude-opus-4-8",
        usage={"input_tokens": 1000, "output_tokens": 200},
        amount=0.02,
        pocket=CostPocket.USER_KEY,
    )
    await recorder.record(
        component="render",
        provider=CostProvider.MANIM,
        model=None,
        usage={"compute_seconds": 12.5},
        amount=0.003,
        pocket=CostPocket.PLATFORM,
    )
    await recorder.finalize()

    # Act — the owner opens the drill-through: the full per-call ledger for the course.
    response = await http_with.get(f"/api/courses/{_COURSE_ID}/cost/events")

    # Assert — every metered call is returned, in emission order, with its measured usage + amount
    # (the auditable "usage x rate" transcript behind the rollup total).
    assert response.status_code == 200
    events = response.json()
    assert [e["seq"] for e in events] == [0, 1]
    assert events[0]["component"] == "planner"
    assert events[0]["provider"] == "anthropic"
    assert events[0]["pocket"] == "user_key"
    assert events[0]["usage"] == {"input_tokens": 1000, "output_tokens": 200}
    assert events[0]["amount"] == pytest.approx(0.02)
    # Multi-word fields serialize camelCase (the web wire contract, via CourseModel's aliases).
    assert events[0]["runId"] == _RUN_ID
    assert events[0]["priceBookVersion"] == _PRICE_BOOK_VERSION
    # The render row round-trips its own measured usage + a null model (render has no model id).
    assert events[1]["provider"] == "manim"
    assert events[1]["pocket"] == "platform"
    assert events[1]["model"] is None
    assert events[1]["usage"] == {"compute_seconds": 12.5}
    assert events[1]["amount"] == pytest.approx(0.003)


async def test_cost_ledger_is_owner_scoped_no_cross_owner_leak(
    event_store: InMemoryCostEventStore,
    subject_cost_store: InMemorySubjectCostStore,
) -> None:
    # Arrange — a build owned by "alice" records cost (the recorder stamps the owner on each write).
    recorder = CostEventRecorder(
        event_store,
        subject_cost_store,
        run_id=_RUN_ID,
        subject_type=CostSubjectType.COURSE,
        subject_id=_COURSE_ID,
        price_book_version=_PRICE_BOOK_VERSION,
        owner_id="alice",
    )
    await recorder.record(
        component="planner",
        provider=CostProvider.ANTHROPIC,
        model="claude-opus-4-8",
        usage={"input_tokens": 1000},
        amount=0.02,
        pocket=CostPocket.USER_KEY,
    )
    await recorder.finalize()

    # Assert — the endpoint's owner-scoping contract (the store the route delegates to): another
    # owner reading the same course's ledger sees nothing, while the owner sees their events.
    assert (
        await event_store.list_for_subject(
            subject_type=CostSubjectType.COURSE,
            subject_id=_COURSE_ID,
            owner_id="bob",
        )
        == []
    )
    theirs = await event_store.list_for_subject(
        subject_type=CostSubjectType.COURSE,
        subject_id=_COURSE_ID,
        owner_id="alice",
    )
    assert [event.seq for event in theirs] == [0]


async def test_cost_ledger_of_an_unmetered_course_is_empty_not_404(
    http_with: httpx.AsyncClient,
) -> None:
    # Act — the drill-through of a course that was never metered.
    response = await http_with.get("/api/courses/never-metered/cost/events")

    # Assert — a 200 empty list (the panel simply has no rows to expand), never a 404.
    assert response.status_code == 200
    assert response.json() == []
