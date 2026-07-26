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
from lunaris_api.cost_recorder import CostEventRecorder
from lunaris_api.dependencies import get_course_cost_store
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemoryCourseCostStore
from lunaris_runtime.schema import CostPocket, CostProvider

_COURSE_ID = "course-skeleton"
_RUN_ID = "run-skeleton"
_PRICE_BOOK_VERSION = "v0-skeleton"


@pytest.fixture
def event_store() -> InMemoryCostEventStore:
    return InMemoryCostEventStore()


@pytest.fixture
def course_cost_store() -> InMemoryCourseCostStore:
    return InMemoryCourseCostStore()


@pytest.fixture
async def http_with(
    course_cost_store: InMemoryCourseCostStore,
) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    # The cost endpoint reads the rollup store; override it so the test's recorder and the endpoint
    # share one instance (auth off → the unscoped single-user path, owner_id is None).
    app.dependency_overrides[get_course_cost_store] = lambda: course_cost_store
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_recorded_cost_rolls_up_and_reads_back_over_http(
    http_with: httpx.AsyncClient,
    event_store: InMemoryCostEventStore,
    course_cost_store: InMemoryCourseCostStore,
) -> None:
    # Arrange — a build records one (stub) metered call, then finalizes to roll the course up.
    recorder = CostEventRecorder(
        event_store,
        course_cost_store,
        run_id=_RUN_ID,
        course_id=_COURSE_ID,
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
    assert body["courseId"] == _COURSE_ID
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
    ledger = await event_store.list_for_course(course_id=_COURSE_ID)
    assert [e.seq for e in ledger] == [0]
    assert ledger[0].component == "walking_skeleton"


async def test_unmetered_course_reads_as_null_not_404(http_with: httpx.AsyncClient) -> None:
    # Act — a course that was never metered (pre-feature, still building, or unknown).
    response = await http_with.get("/api/courses/never-metered/cost")

    # Assert — a 200 null, not a 404: the web renders a "not metered" state, not an error.
    assert response.status_code == 200
    assert response.json() is None
