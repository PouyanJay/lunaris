"""Video V4 acceptance (T4): one end-to-end build that demonstrates the properties V4 promises —
overlap, multi-worker drain, and graceful degrade (plan §V4 Acceptance).

Three modules: A grounds on round 0 (its video enqueues mid-loop and starts while B and C are still
being revised — the overlap), B and C need a revise round. Two workers drain the shared queue; B's
video is forced to FAIL. The build then publishes anyway — A and C carry a READY video, B a FAILED
(retry-state) one — and the canvas Videos phase reports the single degrade (amber on the web).

Scope: the rigorous parallel-drain peak (≥2 concurrent renders) is proven deterministically in
``test_worker_concurrency``; here two workers exercise the multi-worker wiring in a full build and
the build completes without serializing/deadlocking. The narrow variants are covered elsewhere and
re-asserted here in aggregate: the video-off / keyless "zero jobs" gate
(``test_authoring_video_enqueue::test_no_coordinator_enqueues_zero_jobs`` + the apps/api
``test_video_build_gate``), the lesson hero's disabled / failed-retry states
(``LessonVideoHero.test``), and the degrade tally (``test_finalize_video_stitch``).
"""

import asyncio
import contextlib
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
_FIRST_CLEARED_LESSON_ID = "ma-l0"  # module A: grounds on round 0, video starts mid-loop
_FAILING_LESSON_ID = "mb-l0"  # module B: its video render is forced to fail


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


class _OverlapReviser(StubLessonReviser):
    """The deterministic overlap proof from ``test_video_overlap`` — ``revise`` blocks until A's
    video has started, so the authoring loop cannot finish before the overlap has been observed."""

    def __init__(self, *, until: asyncio.Event) -> None:
        super().__init__(_author_fn, _revise_fn)
        self._until = until

    async def revise(
        self, module: Module, cut_claims: Sequence[str], **kwargs: object
    ) -> LessonDraft:
        try:
            async with asyncio.timeout(10):
                await self._until.wait()
        except TimeoutError as exc:
            raise AssertionError("A's video never started — no overlap") from exc
        return await super().revise(module, cut_claims)


class _SelectiveFailPipeline:
    """Signals when A's video starts (overlap) and forces B's render to fail (graceful degrade);
    every other lesson renders the stub video."""

    def __init__(self, *, a_started: asyncio.Event) -> None:
        self._inner = StubVideoPipeline()
        self._a_started = a_started

    async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
        if job.lesson_id == _FIRST_CLEARED_LESSON_ID:
            self._a_started.set()
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


async def test_v4_build_overlaps_videos_with_two_workers_and_degrades_gracefully(
    tmp_path: Path, progress_sink
) -> None:
    # Arrange — the coordinator + two workers over one shared queue; B's render will fail.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    a_started = asyncio.Event()
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01
    )
    draft = _draft(coordinator)
    draft.progress = ProgressReporter("r1", progress_sink)
    pipeline = _SelectiveFailPipeline(a_started=a_started)
    workers = [
        VideoWorker(
            queue=queue, pipeline=pipeline, storage=storage, events=events, worker_id=f"w{n}"
        )
        for n in range(2)
    ]
    worker_tasks = [asyncio.create_task(w.run_forever(poll_interval_seconds=0.01)) for w in workers]
    subgraph = build_authoring_subgraph(_OverlapReviser(until=a_started), _marker_verifier(), draft)
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act — author then finalize; the reviser blocks until A's video has started (the overlap gate).
    try:
        async with asyncio.timeout(20):
            await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})
            result = await finalize.ainvoke({})
    except TimeoutError as exc:
        raise AssertionError("the build did not complete — possible deadlock in finalize") from exc
    finally:
        for task in worker_tasks:
            task.cancel()
        for task in worker_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # Assert — OVERLAP: A's video started while B, C were still being revised; all three enqueued.
    assert a_started.is_set()
    assert len(draft.enqueued_video_jobs) == 3

    # GRACEFUL DEGRADE: the build published anyway despite B's failure.
    assert result["courseId"] == "c1"
    videos = {module.id: module.lessons[0].video for module in draft.course.modules}
    assert videos["ma"] is not None and videos["ma"].status is VideoJobStatus.READY
    assert videos["mc"] is not None and videos["mc"].status is VideoJobStatus.READY
    # B's lesson carries a FAILED retry-state video (no provenance) — never a blocked publish.
    assert videos["mb"] is not None and videos["mb"].status is VideoJobStatus.FAILED
    assert videos["mb"].provenance is None
    # A READY video carries its grounding provenance end to end (structural-provenance contract).
    assert videos["ma"].provenance is not None and videos["ma"].provenance.job_id

    # AMBER CANVAS: the Videos phase reports exactly one degrade out of three, tally + summary text.
    phase = next(e for e in progress_sink.events if e.stage is ProgressStage.LESSON_VIDEOS)
    assert phase.videos_total == 3
    assert phase.videos_degraded == 1
    assert phase.label == "3 lesson videos · 2 ready · 1 needs a retry"
