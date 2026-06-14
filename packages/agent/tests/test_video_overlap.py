"""Video V4-T3: the overlap proof — a lesson's video job starts WHILE authoring continues, not
after it ends (blocking-but-overlapped, plan §0 / §V4-T3).

Deterministic, no wall-clock: three modules, one (A) grounds on round 0 while two (B, C) need a
revise round. A's video job is enqueued at round-0 verify; a worker drains it concurrently. The
reviser's ``revise`` (for B and C) BLOCKS until A's video has STARTED — so the authoring loop can
only finish once that overlap has been observed. The loop completing IS the proof.
"""

import asyncio
import contextlib
from collections.abc import Sequence

from langchain_core.messages import HumanMessage
from lunaris_agent.harness.authoring import build_authoring_subgraph
from lunaris_agent.harness.authoring.stub_reviser import StubLessonReviser
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_runtime.schema import Citation, Module, VideoJob
from lunaris_runtime.video_build import QueueVideoBuildCoordinator
from lunaris_video import StubVideoPipeline, VideoWorker

_GROUNDED = "grounded"
_UNGROUNDABLE = "unsupported"  # claim text with no evidence — forces B and C into a revise round
_OWNER = "user-a"
_FIRST_CLEARED_LESSON_ID = "ma-l0"  # module A grounds on round 0; its video starts mid-loop


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
    # Module A grounds immediately; B and C are ungroundable until revised (forcing a revise round).
    marker = _GROUNDED if module.id == "ma" else _UNGROUNDABLE
    return _lesson(f"{marker} fact about {module.title}")


def _revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
    return _lesson(f"{_GROUNDED} fact about {module.title}")


class _OverlapReviser(StubLessonReviser):
    """A reviser whose ``revise`` blocks until ``until`` is set — so the loop only converges once
    the cleared module's video has started (the overlap we are proving)."""

    def __init__(self, *, until: asyncio.Event) -> None:
        super().__init__(_author_fn, _revise_fn)
        self._until = until

    async def revise(
        self, module: Module, cut_claims: Sequence[str], **kwargs: object
    ) -> LessonDraft:
        try:
            async with asyncio.timeout(10):
                await self._until.wait()
        except (
            TimeoutError
        ) as exc:  # a clear failure, not a confusing TimeoutError through LangGraph
            raise AssertionError("the cleared module's video never started — no overlap") from exc
        return await super().revise(module, cut_claims)


class _StartSignalPipeline:
    """Wraps the stub pipeline; fires ``started`` when the cleared lesson's video is produced."""

    def __init__(self, *, started: asyncio.Event, lesson_id: str) -> None:
        self._inner = StubVideoPipeline()
        self._started = started
        self._lesson_id = lesson_id

    async def produce(self, job: VideoJob, *, on_stage=None) -> object:
        if job.lesson_id == self._lesson_id:
            self._started.set()
        return await self._inner.produce(job, on_stage=on_stage)


def _draft() -> CourseDraft:
    draft = CourseDraft(topic="t", course_id="c1", run_id="r1")
    draft.modules = [
        Module(id="ma", title="A", kcs=["a"], difficulty_index=0.1),
        Module(id="mb", title="B", kcs=["b"], difficulty_index=0.2),
        Module(id="mc", title="C", kcs=["c"], difficulty_index=0.3),
    ]
    return draft


async def test_a_lesson_video_starts_before_authoring_ends() -> None:
    # Arrange — A clears round 0 (its video enqueues mid-loop); B, C need a revise round that blocks
    # until A's video has started. A worker drains the queue concurrently.
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    a_started = asyncio.Event()
    draft = _draft()
    draft.video_coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01
    )
    worker = VideoWorker(
        queue=queue,
        pipeline=_StartSignalPipeline(started=a_started, lesson_id=_FIRST_CLEARED_LESSON_ID),
        storage=storage,
        events=events,
        worker_id="w",
    )
    subgraph = build_authoring_subgraph(_OverlapReviser(until=a_started), _marker_verifier(), draft)
    worker_task = asyncio.create_task(worker.run_forever(poll_interval_seconds=0.01))

    # Act — the loop can only finish if revise unblocks, which needs A's video to have started.
    try:
        async with asyncio.timeout(15):
            await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})
    finally:
        worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker_task

    # Assert — the loop finished, so A's video started WHILE B, C were still being revised (before
    # authoring ended); A's job was enqueued mid-loop, and every module ended up with a video job.
    assert a_started.is_set()
    assert _FIRST_CLEARED_LESSON_ID in draft.enqueued_video_jobs
    assert len(draft.enqueued_video_jobs) == 3
