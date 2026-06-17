"""Video V4 acceptance (T4): one end-to-end build that demonstrates the properties V4 promises —
multi-worker drain + graceful degrade (plan §V4 Acceptance), under the NON-BLOCKING finalize model.

Three modules: A grounds on round 0, B and C need a revise round. Finalize persists the course,
enqueues all three lesson videos, and delivers the course IMMEDIATELY with generating placeholders
(no block on the render). Two workers then drain the shared queue async — B's video forced to FAIL —
and the queue settles 2 READY + 1 FAILED: the graceful degrade the reader's derive-at-read probe
surfaces (the V4 "videos in the payload" fold moved to the reader, PR #110). The build canvas shows
"3 lesson videos generating" (no amber — a still-rendering video is not a failure).

Note: lesson videos no longer overlap authoring (the cloud worker loads the persisted course, so the
enqueue moved to finalize — the "course not found" fix, pinned in ``test_finalize_video_stitch``).
Narrow variants live elsewhere: the video-off / keyless "zero jobs" gate (``test_authoring_video_
enqueue`` + apps/api ``test_video_build_gate``), the lesson hero states (``LessonVideoHero.test``).
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path

from langchain_core.messages import HumanMessage
from lunaris_agent.coverage_critic import StubCoverageCritic
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.authoring import build_authoring_subgraph
from lunaris_agent.harness.authoring.stub_reviser import StubLessonReviser
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.progress_reporter import ProgressReporter
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
from lunaris_video import RenderedVideo, StubVideoPipeline, VideoWorker

_GROUNDED = "grounded"
_UNGROUNDABLE = "unsupported"
_OWNER = "user-a"
_FAILING_LESSON_ID = "mb-l0"  # module B: its video render is forced to fail
_TERMINAL = (VideoJobStatus.READY, VideoJobStatus.FAILED)


def _marker_verifier() -> Verifier:
    retriever = StubEvidenceRetriever(
        lambda claim: (
            [Evidence(citation=Citation(id="s", title="R", snippet=claim), score=0.9)]
            if _GROUNDED in claim
            else []
        )
    )
    return Verifier(retriever, StubSupportAssessor())


def _lesson(text: str) -> LessonDraft:
    return LessonDraft(
        activate=SegmentDraft("Recall.", []),
        demonstrate=SegmentDraft("Example.", [text]),
        apply=SegmentDraft("Apply.", []),
        integrate=SegmentDraft("Integrate.", []),
    )


def _author_fn(module: Module) -> LessonDraft:
    marker = _GROUNDED if module.id == "ma" else _UNGROUNDABLE
    return _lesson(f"{marker} fact about {module.title}")


def _revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
    return _lesson(f"{_GROUNDED} fact about {module.title}")


class _FailModuleBPipeline:
    """Forces B's render to fail (graceful degrade); every other lesson renders the stub video."""

    def __init__(self) -> None:
        self._inner = StubVideoPipeline()

    async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
        if job.lesson_id == _FAILING_LESSON_ID:
            raise RuntimeError("render exploded for module B")
        return await self._inner.produce(job)


def _draft(coordinator: QueueVideoBuildCoordinator) -> CourseDraft:
    draft = CourseDraft(topic="t", course_id="c1", run_id="r1")
    draft.modules = [
        Module(id="ma", title="A", kcs=["a"], difficulty_index=0.1),
        Module(id="mb", title="B", kcs=["b"], difficulty_index=0.2),
        Module(id="mc", title="C", kcs=["c"], difficulty_index=0.3),
    ]
    draft.graph = PrerequisiteGraph(
        nodes=[
            KnowledgeComponent(
                id=kc,
                label=kc.upper(),
                definition="d",
                difficulty=0.2,
                bloom_ceiling=BloomLevel.UNDERSTAND,
            )
            for kc in ("a", "b", "c")
        ],
        edges=[],
        frontier=[],
        is_acyclic=True,
        topo_order=["a", "b", "c"],
    )
    draft.video_coordinator = coordinator
    return draft


async def test_v4_build_enqueues_videos_then_two_workers_render_them_async(
    tmp_path: Path, progress_sink
) -> None:
    # Arrange — the coordinator over a shared queue; NO workers run during finalize (non-blocking:
    # finalize must deliver without waiting on the render). B's render is forced to fail later.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01
    )
    draft = _draft(coordinator)
    draft.progress = ProgressReporter("r1", progress_sink)
    subgraph = build_authoring_subgraph(
        StubLessonReviser(_author_fn, _revise_fn), _marker_verifier(), draft
    )
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act 1 — author (enqueues nothing now), then finalize persists + enqueues all three and
    # delivers the course IMMEDIATELY. The tight timeout would trip if finalize blocked on a render.
    async with asyncio.timeout(5):
        await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})
        assert draft.enqueued_video_jobs == {}  # authoring enqueued nothing
        result = await finalize.ainvoke({})

    # Assert finalize — published immediately; every lesson carries a GENERATING placeholder (FAILED
    # + job_id, no provenance) the reader's derive-at-read probe recovers once the worker finishes.
    assert len(draft.enqueued_video_jobs) == 3
    assert result["courseId"] == "c1"
    videos = {module.id: module.lessons[0].video for module in draft.course.modules}
    for video in videos.values():
        assert video is not None and video.status is VideoJobStatus.FAILED and video.job_id
        assert video.provenance is None
    # The Videos phase reads "generating" (rendering async), never "needs a retry" — no amber.
    phase = next(e for e in progress_sink.events if e.stage is ProgressStage.LESSON_VIDEOS)
    assert phase.videos_total == 3
    assert phase.videos_degraded == 0
    assert phase.label == "3 lesson videos generating"

    # Act 2 — two workers now drain the shared queue async (B's render forced to fail); render every
    # job to a terminal state. The multi-worker drain that used to overlap the blocking await.
    pipeline = _FailModuleBPipeline()
    workers = [
        VideoWorker(
            queue=queue, pipeline=pipeline, storage=storage, events=events, worker_id=f"w{n}"
        )
        for n in range(2)
    ]
    async with asyncio.timeout(20):
        while True:
            await asyncio.gather(*(worker.run_once() for worker in workers))
            jobs = await queue.list_for_course(course_id="c1", owner_id=_OWNER)
            if jobs and all(job.status in _TERMINAL for job in jobs):
                break

    # Assert async outcome — GRACEFUL DEGRADE at the queue level (what derive-at-read surfaces): A
    # and C render READY; B's forced failure settles FAILED. The build published; nothing got stuck.
    final = {
        job.lesson_id: job for job in await queue.list_for_course(course_id="c1", owner_id=_OWNER)
    }
    assert final["ma-l0"].status is VideoJobStatus.READY
    assert final["mc-l0"].status is VideoJobStatus.READY
    assert final["mb-l0"].status is VideoJobStatus.FAILED
    # The placeholder's job_id IS the queue job the reader probes — the full derive-at-read chain.
    assert videos["ma"].job_id == final["ma-l0"].id
