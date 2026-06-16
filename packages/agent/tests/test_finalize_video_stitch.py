"""Video V4-T1 (with the cloud-worker ordering fix): finalize PERSISTS the course, then enqueues a
lesson-video job for every lesson, awaits them, and stitches each finished artifact into its lesson
— blocking, degrade-on-failure (plan §V4-T1).

Persist-before-enqueue is the fix for the prod "course not found" race: the cloud worker renders a
lesson video by loading the course from the store, so the course must already be saved when the job
is enqueued (the V4 in-process worker shared memory and never hit this; the V7 cloud worker reads
the DB). A failed job never blocks publication — its lesson publishes with a FAILED (retry-state)
video. Driven keyless end to end: real coordinator + real worker (stub pipeline) + real finalize,
with the worker draining in the background so it picks up whatever finalize enqueues.
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
from lunaris_runtime.video_build import QueueVideoBuildCoordinator
from lunaris_video import StubVideoPipeline, VideoWorker
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


async def test_finalize_enqueues_then_stitches_a_ready_video_into_its_lesson(
    tmp_path: Path,
) -> None:
    # Arrange — author (no enqueue), then finalize with a worker draining concurrently. The job is
    # created BY finalize, so finalize must block on it (the worker renders it during the await).
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
    assert draft.enqueued_video_jobs == {}  # authoring enqueued nothing — finalize will

    # Act
    await _finalize_draining(
        draft,
        CourseStore(tmp_path),
        queue=queue,
        storage=storage,
        events=events,
        pipeline=StubVideoPipeline(),
    )

    # Assert — the lesson carries a READY video whose structural provenance traces the job it came
    # from (provenance is populated, not just an MP4 reference).
    lesson = draft.course.modules[0].lessons[0]
    assert lesson.video is not None
    assert lesson.video.status is VideoJobStatus.READY
    assert lesson.video.provenance is not None
    assert lesson.video.provenance.job_id == draft.enqueued_video_jobs[lesson.id]
    assert lesson.video.provenance.course_id == "c1"


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


async def test_finalize_emits_a_videos_phase_with_per_lesson_beats(
    tmp_path: Path, progress_sink, agent_sink
) -> None:
    # Arrange — a shared cursor across both reporters, exactly as the runner wires them, so beats
    # bucket under the phase active when they fire (the canvas Videos phase, V4-T2).
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01
    )
    draft = _draft_with_graph(coordinator)
    cursor = StageCursor()
    draft.progress = ProgressReporter("r1", progress_sink, cursor=cursor)
    draft.agent = AgentReporter("r1", agent_sink, cursor=cursor)
    await _author(draft)

    # Act
    await _finalize_draining(
        draft,
        CourseStore(tmp_path),
        queue=queue,
        storage=storage,
        events=events,
        pipeline=StubVideoPipeline(),
    )

    # Assert — one LESSON_VIDEOS progress beat carrying the tally + summary (none degraded here)…
    videos = [e for e in progress_sink.events if e.stage is ProgressStage.LESSON_VIDEOS]
    assert len(videos) == 1
    assert videos[0].videos_total == 1
    assert videos[0].videos_degraded == 0
    assert videos[0].label == "1 lesson video ready"
    # …and exactly one per-lesson line, stamped INTO the Videos phase (the canvas buckets it there).
    video_beats = [e for e in agent_sink.events if e.stage is ProgressStage.LESSON_VIDEOS]
    assert len(video_beats) == 1
    assert video_beats[0].text == "Explainer video for “Routing” is ready."


async def test_finalize_videos_phase_reports_a_degraded_count(
    tmp_path: Path, progress_sink, agent_sink
) -> None:
    # Arrange — a failing pipeline so the one lesson video degrades.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01
    )
    draft = _draft_with_graph(coordinator)
    cursor = StageCursor()
    draft.progress = ProgressReporter("r1", progress_sink, cursor=cursor)
    draft.agent = AgentReporter("r1", agent_sink, cursor=cursor)
    await _author(draft)

    # Act
    await _finalize_draining(
        draft,
        CourseStore(tmp_path),
        queue=queue,
        storage=storage,
        events=events,
        pipeline=_FailingPipeline(),
    )

    # Assert — the Videos phase reports the degrade in both the tally and the summary (web → amber)…
    videos = next(e for e in progress_sink.events if e.stage is ProgressStage.LESSON_VIDEOS)
    assert videos.videos_total == 1
    assert videos.videos_degraded == 1
    assert videos.label == "1 lesson video · 0 ready · 1 needs a retry"
    # …and the per-lesson line carries the retry call-to-action.
    video_beats = [e for e in agent_sink.events if e.stage is ProgressStage.LESSON_VIDEOS]
    assert len(video_beats) == 1
    assert "could not be generated" in video_beats[0].text


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
