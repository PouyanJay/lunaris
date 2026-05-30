from pathlib import Path

from lunaris_agent import build_stub_orchestrator
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import CourseStatus, ProgressEvent, ProgressStage


class _RecordingSink:
    """An IProgressSink that captures every emitted event for assertions."""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)


async def test_pipeline_emits_ordered_progress_events(tmp_path: Path) -> None:
    # Arrange — the deterministic stub pipeline (5 KCs → 5 modules), recording sink.
    store = CourseStore(tmp_path)
    orchestrator = build_stub_orchestrator(store)
    sink = _RecordingSink()

    # Act
    course = await orchestrator.run("binary search", course_id="c1", run_id="run-9", progress=sink)

    # Assert — the full ordered stage backbone, one MODULE_AUTHORED per module.
    stages = [e.stage for e in sink.events]
    assert stages == [
        ProgressStage.RUN_STARTED,
        ProgressStage.CONCEPTS_EXTRACTED,
        ProgressStage.GRAPH_BUILT,
        ProgressStage.CURRICULUM_DESIGNED,
        *([ProgressStage.MODULE_AUTHORED] * len(course.modules)),
        ProgressStage.CLAIMS_VERIFIED,
        ProgressStage.RUN_COMPLETED,
    ]

    # run_id correlation across every event; sequence is a monotonic 0..N ordinal.
    assert all(e.run_id == "run-9" for e in sink.events)
    assert [e.sequence for e in sink.events] == list(range(len(sink.events)))

    # Every event carries a human-readable label.
    assert all(e.label for e in sink.events)

    # Stage-specific counts are populated.
    graph = next(e for e in sink.events if e.stage is ProgressStage.GRAPH_BUILT)
    assert graph.kc_count == len(course.graph.nodes)
    assert graph.edge_count == len(course.graph.edges)

    curriculum = next(e for e in sink.events if e.stage is ProgressStage.CURRICULUM_DESIGNED)
    assert curriculum.module_count == len(course.modules)

    authored_ids = [e.module_id for e in sink.events if e.stage is ProgressStage.MODULE_AUTHORED]
    assert authored_ids == [m.id for m in course.modules]

    verified = next(e for e in sink.events if e.stage is ProgressStage.CLAIMS_VERIFIED)
    assert verified.claims_total >= 1
    assert verified.claims_supported + verified.claims_cut == verified.claims_total

    completed = sink.events[-1]
    assert completed.status is CourseStatus.PUBLISHED
    assert course.status is CourseStatus.PUBLISHED


async def test_run_without_sink_still_completes(tmp_path: Path) -> None:
    # Arrange — the NoOp default must keep existing call sites (no progress arg) working.
    store = CourseStore(tmp_path)
    orchestrator = build_stub_orchestrator(store)

    # Act
    course = await orchestrator.run("binary search", course_id="c2", run_id="run-10")

    # Assert
    assert course.status is CourseStatus.PUBLISHED
