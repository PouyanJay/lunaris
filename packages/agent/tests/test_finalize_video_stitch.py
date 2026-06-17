"""Finalize's lesson-video handling: PERSIST the course, enqueue a lesson-video job for every
lesson, then fold a placeholder per job — WITHOUT blocking on the render (the cloud worker finishes
each minutes later; the reader's derive-at-read probe recovers them). Non-blocking, plan §0.

Persist-before-enqueue is the fix for the prod "course not found" race: the cloud worker renders a
lesson video by loading the course from the store, so the course must already be saved when the job
is enqueued (the V4 in-process worker shared memory and never hit this; the V7 cloud worker reads
the DB). A video never blocks publication. Driven keyless: real coordinator (await timeout 0) + real
finalize; one surviving test still drains a background worker to settle a job before its collect.
"""

import asyncio
import contextlib
from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import HumanMessage
from lunaris_agent.coverage_critic import StubCoverageCritic
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.agent_reporter import AgentReporter
from lunaris_agent.harness.authoring import build_authoring_subgraph
from lunaris_agent.harness.authoring.stub_reviser import StubLessonReviser
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.progress_reporter import ProgressReporter
from lunaris_agent.harness.stage_cursor import StageCursor
from lunaris_agent.harness.tools import make_finalize_course_tool
from lunaris_agent.harness.tools.finalize_course import (
    _video_beat,
    _VideoOutcome,
    _videos_label,
)
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.persistence import (
    CourseStore,
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_runtime.schema import (
    BloomLevel,
    Citation,
    KnowledgeComponent,
    Module,
    PrerequisiteGraph,
    ProgressStage,
    VideoJob,
    VideoJobStatus,
)
from lunaris_runtime.video_build import QueueVideoBuildCoordinator, VideoConfig
from lunaris_video import VideoWorker
from lunaris_video.models.rendered_video import RenderedVideo

_GROUNDED = "grounded"
_OWNER = "user-a"


def _marker_verifier() -> Verifier:
    retriever = StubEvidenceRetriever(
        lambda claim: (
            [
                Evidence(
                    citation=Citation(id=f"s::{claim[:12]}", title="R", snippet=claim), score=0.9
                )
            ]
            if _GROUNDED in claim
            else []
        )
    )
    return Verifier(retriever, StubSupportAssessor())


def _grounded_author(module: Module) -> LessonDraft:
    return LessonDraft(
        activate=SegmentDraft("Recall.", []),
        demonstrate=SegmentDraft("Example.", [f"{_GROUNDED} fact about {module.title}"]),
        apply=SegmentDraft("Apply.", []),
        integrate=SegmentDraft("Integrate.", []),
    )


def _unused_revise(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
    return _grounded_author(module)


def _draft_with_graph(coordinator: object) -> CourseDraft:
    draft = CourseDraft(topic="t", course_id="c1", run_id="r1")
    draft.modules = [Module(id="m0", title="Routing", kcs=["c"], difficulty_index=0.5)]
    draft.graph = PrerequisiteGraph(
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
    draft.video_coordinator = coordinator  # type: ignore[assignment]
    return draft


async def _author(draft: CourseDraft) -> None:
    """Run the authoring loop. It authors the lessons but — since the cloud-worker ordering fix —
    enqueues NO video jobs (that moved to finalize, after the persist)."""
    subgraph = build_authoring_subgraph(
        StubLessonReviser(_grounded_author, _unused_revise), _marker_verifier(), draft
    )
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})


async def _finalize_draining(
    draft: CourseDraft,
    store: CourseStore,
    *,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    pipeline: object,
) -> dict[str, object]:
    """Run finalize with a worker draining in the background. The worker runs forever (not run_once)
    because the jobs don't exist until finalize enqueues them — a run_once before finalize would
    claim nothing, leaving finalize's collect to poll forever."""
    worker = VideoWorker(
        queue=queue,
        pipeline=pipeline,  # type: ignore[arg-type]
        storage=storage,
        events=events,
        worker_id="w",
    )
    task = asyncio.create_task(worker.run_forever(poll_interval_seconds=0.01))
    finalize = make_finalize_course_tool(MinimalCritic(), store, draft, StubCoverageCritic())
    try:
        async with asyncio.timeout(15):
            return await finalize.ainvoke({})
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_finalize_persists_course_before_enqueuing_lesson_videos(tmp_path: Path) -> None:
    # The fix: the cloud worker renders a lesson video by loading the course from the store, so
    # finalize must persist BEFORE it enqueues — otherwise the worker fails "course not found". A
    # spy coordinator does what the worker's lesson provider does (load the course) at enqueue time;
    # it must already be there.
    store = CourseStore(tmp_path)
    loaded_at_enqueue: list[str] = []

    class _OrderingCoordinator:
        async def enqueue_lesson(self, *, course_id: str, lesson_id: str, content_hash: str) -> str:
            store.load(course_id)  # raises FileNotFoundError if finalize hasn't persisted yet
            loaded_at_enqueue.append(course_id)
            return f"job-{lesson_id}"

        async def collect(self, jobs_by_lesson: object) -> dict[str, object]:
            return {}

        async def collect_course_videos(self, jobs: object) -> dict[object, object]:
            return {}

    draft = _draft_with_graph(_OrderingCoordinator())
    await _author(draft)

    # Act
    finalize = make_finalize_course_tool(MinimalCritic(), store, draft, StubCoverageCritic())
    await finalize.ainvoke({})

    # Assert — a lesson video was enqueued, and the course was already loadable from the store at
    # that moment (no FileNotFoundError) — the ordering that prevents "course not found".
    assert loaded_at_enqueue == ["c1"]


async def test_finalize_does_not_block_and_folds_a_generating_placeholder(
    tmp_path: Path, progress_sink, agent_sink
) -> None:
    """Non-blocking finalize (the fix for the build-canvas 'stuck on Verify' silent gap): finalize
    enqueues the lesson videos and delivers the course WITHOUT the 900s collect block — the cloud
    worker renders each video minutes later and the reader's derive-at-read probe recovers it. Each
    lesson is folded as a FAILED-with-job_id PLACEHOLDER carrying the job id the reader probes by;
    the Videos phase reads 'generating' (rendering async), not 'needs a retry' (not failed).
    """
    # Arrange — a coordinator that does NOT wait (await_timeout_s=0, the new default) and NO worker:
    # the enqueued lesson video stays QUEUED, exactly the cloud-worker reality at finalize time.
    queue, storage = InMemoryVideoJobQueue(), InMemoryVideoStorage()
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, await_timeout_s=0.0, poll_s=0.01
    )
    draft = _draft_with_graph(coordinator)
    cursor = StageCursor()
    draft.progress = ProgressReporter("r1", progress_sink, cursor=cursor)
    draft.agent = AgentReporter("r1", agent_sink, cursor=cursor)
    await _author(draft)

    # Act — finalize with NO draining worker; it must return promptly (the timeout would trip at the
    # 900s mark if finalize still blocked on the collect).
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )
    async with asyncio.timeout(5):
        result = await finalize.ainvoke({})

    # Assert — published, and the lesson carries a recoverable placeholder (FAILED + job_id, no
    # provenance) the reader's coordinate probe resolves once the worker finishes.
    assert result["status"] in ("published", "review")
    lesson = draft.course.modules[0].lessons[0]
    assert lesson.video is not None
    assert lesson.video.status is VideoJobStatus.FAILED
    assert lesson.video.job_id == draft.enqueued_video_jobs[lesson.id]
    assert lesson.video.provenance is None
    # The Videos phase reads 'generating', not 'needs a retry' (rendering async, not failed).
    videos = next(e for e in progress_sink.events if e.stage is ProgressStage.LESSON_VIDEOS)
    assert videos.videos_total == 1
    assert videos.videos_degraded == 0
    assert "generating" in videos.label.lower()
    beats = [e for e in agent_sink.events if e.stage is ProgressStage.LESSON_VIDEOS]
    assert len(beats) == 1
    assert "generating" in beats[0].text.lower()


def test_videos_label_reads_generating_not_failed_for_unfinished_videos() -> None:
    # The non-blocking phase summary: unfinished videos read "generating" (they render async), never
    # "needs a retry"; an already-finished one reads "ready"; a mix shows both counts.
    assert _videos_label(1, 0, 1) == "1 lesson video generating"
    assert _videos_label(3, 0, 3) == "3 lesson videos generating"
    assert _videos_label(2, 2, 0) == "2 lesson videos ready"
    assert _videos_label(3, 1, 2) == "3 lesson videos · 1 ready · 2 generating"


def test_video_beat_reads_generating_for_an_unfinished_video() -> None:
    assert _video_beat(_VideoOutcome("Routing", is_ready=True)) == (
        "Explainer video for “Routing” is ready."
    )
    assert _video_beat(_VideoOutcome("Routing", is_ready=False)) == (
        "Explainer video for “Routing” is generating in the background."
    )


async def test_finalize_publishes_anyway_when_a_video_fails(tmp_path: Path) -> None:
    # Arrange — a pipeline that always fails; the worker settles the job FAILED.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01
    )
    draft = _draft_with_graph(coordinator)
    await _author(draft)

    # Act — the failed video must NOT block the course.
    result = await _finalize_draining(
        draft,
        CourseStore(tmp_path),
        queue=queue,
        storage=storage,
        events=events,
        pipeline=_FailingPipeline(),
    )

    # Assert — the course still finalized; the lesson carries a FAILED (retry-state) video that, as
    # a video that never planned a contract, carries no provenance.
    assert result["courseId"] == "c1"
    lesson = draft.course.modules[0].lessons[0]
    assert lesson.video is not None
    assert lesson.video.status is VideoJobStatus.FAILED
    assert lesson.video.provenance is None


async def test_finalize_skips_lesson_videos_when_the_lessons_toggle_is_off(
    tmp_path: Path, progress_sink
) -> None:
    # The per-lesson sub-toggle OFF, master still on (the coordinator IS wired, so the course-level
    # videos still enqueue — proven in test_course_video_build). The build authors a real lesson,
    # but finalize must enqueue ZERO lesson videos: no worker capacity spent on per-lesson renders.
    queue = InMemoryVideoJobQueue()
    coordinator = QueueVideoBuildCoordinator(
        queue=queue,
        storage=InMemoryVideoStorage(),
        owner_id=_OWNER,
        video_config=VideoConfig(
            enabled=True,
            voice=True,
            lessons_enabled=False,
            summary_seconds=75,
            overview_seconds=180,
            lesson_seconds=75,
        ),
    )
    draft = _draft_with_graph(coordinator)
    draft.progress = ProgressReporter("r1", progress_sink, cursor=StageCursor())
    await _author(draft)

    # Act — finalize persists the course and would enqueue per-lesson videos; the gate declines.
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )
    result = await finalize.ainvoke({})

    # Assert — published with a real authored lesson, but no lesson video: nothing tracked, nothing
    # claimable, no placeholder folded, and no vacuous Videos phase opened.
    assert result["status"] in ("published", "review")
    lessons = draft.course.modules[0].lessons
    assert lessons  # authoring genuinely populated the module (the gate must be the only reason)
    assert draft.enqueued_video_jobs == {}
    assert await queue.claim(worker_id="w") is None
    assert lessons[0].video is None
    assert not any(e.stage is ProgressStage.LESSON_VIDEOS for e in progress_sink.events)


async def test_finalize_emits_no_videos_phase_when_there_are_no_lessons(
    tmp_path: Path, progress_sink
) -> None:
    # Arrange — a coordinator is wired but nothing was authored (the course has no lessons), so
    # finalize enqueues no lesson videos.
    coordinator = QueueVideoBuildCoordinator(
        queue=InMemoryVideoJobQueue(), storage=InMemoryVideoStorage(), owner_id=_OWNER
    )
    draft = _draft_with_graph(coordinator)
    draft.progress = ProgressReporter("r1", progress_sink, cursor=StageCursor())
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act — finalize with no lessons to enqueue.
    await finalize.ainvoke({})

    # Assert — no Videos phase is opened (the canvas leaves it pending), no vacuous 0/0 tally.
    assert not any(e.stage is ProgressStage.LESSON_VIDEOS for e in progress_sink.events)


class _FailingPipeline:
    """A pipeline whose produce always raises — to prove finalize degrades, never blocks."""

    async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
        raise RuntimeError("render exploded")
