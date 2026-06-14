"""Video V5-T2: course-level videos in the build — the SUMMARY trailer + OVERVIEW intro enqueue once
the curriculum is designed, a worker drains them, and ``finalize_course`` folds them into
``Course.videos`` (the Overview section), blocking-but-overlapped, degrade-on-failure.

Driven end to end on the real seam: the enqueue hook → real coordinator → real worker (stub) → real
finalize. The gate (video off ⇒ no coordinator ⇒ no course videos) is proven too.
"""

import asyncio
from pathlib import Path

from lunaris_agent.coverage_critic import StubCoverageCritic
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_finalize_course_tool
from lunaris_agent.harness.tools.design_curriculum import _enqueue_course_videos
from lunaris_runtime.persistence import (
    CourseStore,
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_runtime.schema import (
    BloomLevel,
    CourseBrief,
    KnowledgeComponent,
    Module,
    PrerequisiteGraph,
    VideoJob,
    VideoJobStatus,
    VideoKind,
)
from lunaris_runtime.video_build import QueueVideoBuildCoordinator
from lunaris_video import StubVideoPipeline, VideoWorker
from lunaris_video.models.rendered_video import RenderedVideo

_OWNER = "user-a"


def _graph() -> PrerequisiteGraph:
    return PrerequisiteGraph(
        nodes=[
            KnowledgeComponent(
                id="c",
                label="C",
                definition="d",
                difficulty=0.2,
                bloom_ceiling=BloomLevel.UNDERSTAND,
            )
        ],
        edges=[],
        frontier=[],
        is_acyclic=True,
        topo_order=["c"],
    )


def _draft(coordinator: QueueVideoBuildCoordinator | None) -> CourseDraft:
    draft = CourseDraft(topic="Algorithms", course_id="c1", run_id="r1")
    draft.modules = [Module(id="m0", title="Sorting", kcs=["c"], difficulty_index=0.5)]
    draft.graph = _graph()
    draft.brief = CourseBrief(subject="Algorithms", goal="reason about cost")
    draft.video_coordinator = coordinator
    return draft


def _coordinator(
    queue: InMemoryVideoJobQueue, storage: InMemoryVideoStorage
) -> QueueVideoBuildCoordinator:
    return QueueVideoBuildCoordinator(queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01)


# ── the enqueue hook (design_curriculum) ───────────────────────────────────────────────


async def test_curriculum_design_enqueues_both_course_videos() -> None:
    # Arrange
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    draft = _draft(_coordinator(queue, storage))

    # Act — the hook design_curriculum runs after CURRICULUM_DESIGNED.
    await _enqueue_course_videos(draft)

    # Assert — one SUMMARY + one OVERVIEW job tracked on the draft and queued.
    assert set(draft.enqueued_course_videos) == {VideoKind.SUMMARY, VideoKind.OVERVIEW}
    kinds = {(await queue.claim(worker_id="w")).kind for _ in range(2)}  # type: ignore[union-attr]
    assert kinds == {VideoKind.SUMMARY, VideoKind.OVERVIEW}


async def test_no_coordinator_enqueues_nothing() -> None:
    # Arrange / Act — video off (no coordinator): the hook is a no-op (the gate is the composition
    # root's; the harness only checks presence).
    draft = _draft(coordinator=None)
    await _enqueue_course_videos(draft)

    # Assert
    assert draft.enqueued_course_videos == {}


async def test_a_briefless_build_enqueues_only_the_summary() -> None:
    # Arrange — a direct-assembly build with no brief has nothing to ground the OVERVIEW intro.
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    draft = _draft(_coordinator(queue, storage))
    draft.brief = None

    # Act
    await _enqueue_course_videos(draft)

    # Assert — the curriculum-grounded SUMMARY still enqueues; the OVERVIEW is skipped.
    assert set(draft.enqueued_course_videos) == {VideoKind.SUMMARY}


# ── finalize stitches Course.videos ─────────────────────────────────────────────────────


async def test_finalize_stitches_both_course_videos_into_the_overview_section(
    tmp_path: Path,
) -> None:
    # Arrange — enqueue both (as design_curriculum does), then a worker drains concurrently with
    # finalize: the jobs are NOT done when finalize is called, so this proves finalize BLOCKS on it.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    draft = _draft(_coordinator(queue, storage))
    await _enqueue_course_videos(draft)
    worker = VideoWorker(
        queue=queue, pipeline=StubVideoPipeline(), storage=storage, events=events, worker_id="w"
    )
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act — finalize and two worker drains race; finalize's await waits for both jobs. Two
    # run_once() calls are needed (the queue serialises claims, one job each); a single drain would
    # leave the second job QUEUED and finalize would block on it until the timeout.
    await asyncio.gather(finalize.ainvoke({}), worker.run_once(), worker.run_once())

    # Assert — the course opens with both videos, each READY with provenance tracing its job + kind.
    videos = draft.course.videos
    assert videos is not None
    assert videos.summary is not None and videos.summary.status is VideoJobStatus.READY
    assert videos.summary.kind is VideoKind.SUMMARY
    assert videos.summary.provenance.job_id == draft.enqueued_course_videos[VideoKind.SUMMARY]
    assert videos.overview is not None and videos.overview.status is VideoJobStatus.READY
    assert videos.overview.kind is VideoKind.OVERVIEW
    assert videos.overview.provenance.job_id == draft.enqueued_course_videos[VideoKind.OVERVIEW]


async def test_finalize_publishes_anyway_when_a_course_video_fails(tmp_path: Path) -> None:
    # Arrange — a pipeline that always fails; both course videos settle FAILED.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    draft = _draft(_coordinator(queue, storage))
    await _enqueue_course_videos(draft)
    worker = VideoWorker(
        queue=queue, pipeline=_FailingPipeline(), storage=storage, events=events, worker_id="w"
    )
    await worker.run_once()
    await worker.run_once()
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act — the failed course videos must NOT block the course.
    result = await finalize.ainvoke({})

    # Assert — the course still finalized; the Overview section carries FAILED (retry-state) videos
    # with no provenance (they never planned a contract).
    assert result["courseId"] == "c1"
    videos = draft.course.videos
    assert videos.summary.status is VideoJobStatus.FAILED
    assert videos.summary.provenance is None
    assert videos.overview.status is VideoJobStatus.FAILED


async def test_finalize_leaves_videos_none_when_video_is_off(tmp_path: Path) -> None:
    # Arrange — no coordinator (video off): nothing enqueued, so the course has no Overview section.
    draft = _draft(coordinator=None)
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act
    await finalize.ainvoke({})

    # Assert — backward compatible: a video-off build finalizes with Course.videos absent.
    assert draft.course.videos is None


class _FailingPipeline:
    """A pipeline whose produce always raises — to prove finalize degrades, never blocks."""

    async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
        raise RuntimeError("render exploded")
