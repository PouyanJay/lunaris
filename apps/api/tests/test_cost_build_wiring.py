"""Integration test for the cost-scope build-boundary wiring (course-cost-metering, T4).

Proves the seam end to end through the REAL ``CourseService.create``: a build enters a
``cost_scope`` around its task, so a deep ``record_cost`` while the pipeline runs buffers on it,
and the boundary drains it to the ledger + rollup once the build finishes. The pipeline is a stub
(no live Claude in CI) that records a cost and then delegates to the real stub orchestrator for a
valid Course — so only the paid call is simulated; the scope entry, task inheritance, and drain are
all real.
"""

from pathlib import Path

import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.run_registry import RunRegistry
from lunaris_api.service import CourseService
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.metering import record_cost
from lunaris_runtime.persistence import (
    CourseStore,
    InMemoryCostEventStore,
    InMemoryRunStore,
    InMemorySubjectCostStore,
)
from lunaris_runtime.schema import CostPocket, CostProvider, CostSubjectType, CostUnit, Course

_OPUS = "claude-opus-4-8"


class _MeteringStubPipeline:
    """Records one (simulated) Claude call's cost, then builds a real Course via the stub."""

    def __init__(self, store: object) -> None:
        self._inner = build_stub_orchestrator(store)  # type: ignore[arg-type]

    async def run(self, topic: str, *, course_id: str, run_id: str, **kwargs: object) -> Course:
        # A "deep" paid call during the build — lands in the run's cost_scope. component="llm"
        # matches what real Claude seams record today (per-subagent labels are a documented
        # follow-up); the metering vertical this exercises is provider/pocket/total, not the label.
        record_cost(
            component="llm",
            provider=CostProvider.ANTHROPIC,
            model=_OPUS,
            usage={CostUnit.INPUT_TOKENS: 1_000_000, CostUnit.OUTPUT_TOKENS: 1_000_000},  # $5 + $25
        )
        return await self._inner.run(topic, course_id=course_id, run_id=run_id, **kwargs)  # type: ignore[return-value]


def _service(
    tmp_path: Path,
    *,
    event_store: InMemoryCostEventStore | None = None,
    cost_store: InMemorySubjectCostStore | None = None,
) -> CourseService:
    return CourseService(
        CourseStore(tmp_path),
        lambda store: _MeteringStubPipeline(store),
        InMemoryRunStore(),
        RunRegistry(),
        cost_event_store=event_store,
        subject_cost_store=cost_store,
    )


async def test_build_records_claude_cost_through_the_scope(tmp_path: Path) -> None:
    # Arrange
    clear_correlation()
    event_store, cost_store = InMemoryCostEventStore(), InMemorySubjectCostStore()
    service = _service(tmp_path, event_store=event_store, cost_store=cost_store)

    # Act — run a real build; the stub pipeline records a Claude cost inside the build task.
    course = await service.create("graphs", course_id="c-wired", run_id="run-wired")

    # Assert — the scope was entered around the task and drained at the boundary: the cost reached
    # the rollup (and the ledger) with the calculated total.
    rollup = await cost_store.get(subject_type=CostSubjectType.COURSE, subject_id=course.id)
    assert rollup is not None
    assert rollup.total_amount == pytest.approx(30.0)  # $5 input + $25 output
    assert rollup.breakdown["byProvider"]["anthropic"] == pytest.approx(30.0)
    # Auth off → the unscoped single-user path bills the platform pocket (no tenant key in scope).
    assert rollup.breakdown["byPocket"]["platform"] == pytest.approx(30.0)
    ledger = await event_store.list_for_subject(
        subject_type=CostSubjectType.COURSE,
        subject_id=course.id,
    )
    assert [e.component for e in ledger] == ["llm"]
    assert ledger[0].pocket is CostPocket.PLATFORM


async def test_stream_build_records_claude_cost_through_the_durable_task(tmp_path: Path) -> None:
    # The SSE build path enters the cost_scope around the DURABLE task (_run_recording_status) and
    # drains from its finally — so a build recorded over the stream still rolls its cost up, even
    # though the drain lives on a different task than create()'s.
    clear_correlation()
    event_store, cost_store = InMemoryCostEventStore(), InMemorySubjectCostStore()
    service = _service(tmp_path, event_store=event_store, cost_store=cost_store)

    # Drain the whole stream so the durable build task runs to completion (and its finally drains).
    async for _item in service.stream("graphs", course_id="c-stream", run_id="run-stream"):
        pass

    rollup = await cost_store.get(subject_type=CostSubjectType.COURSE, subject_id="c-stream")
    assert rollup is not None
    assert rollup.total_amount == pytest.approx(30.0)
    assert rollup.breakdown["byProvider"]["anthropic"] == pytest.approx(30.0)


async def test_build_without_cost_stores_records_nothing(tmp_path: Path) -> None:
    # A service with no cost stores (batch / tests) leaves metering off — the build still succeeds.
    clear_correlation()
    service = _service(tmp_path)
    course = await service.create("graphs", course_id="c-nometer", run_id="run-nometer")
    assert course.id == "c-nometer"
