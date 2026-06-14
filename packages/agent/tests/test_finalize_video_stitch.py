"""Video V4-T1: finalize awaits the build's enqueued lesson videos and stitches each finished
artifact into its lesson — blocking-but-overlapped, degrade-on-failure (plan §V4-T1).

The author→verify→revise loop enqueues a lesson-video job (V4-T0); a worker drains it concurrently;
``finalize_course`` then awaits the jobs and folds each ``VideoArtifact`` into ``Lesson.video``. A
job that fails never blocks publication — its lesson publishes with a FAILED (retry-state) video.
Driven keyless end to end: real coordinator + real worker (stub pipeline) + real finalize.
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


def _draft_with_graph(coordinator: QueueVideoBuildCoordinator) -> CourseDraft:
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
    draft.video_coordinator = coordinator
    return draft


async def _author_and_enqueue(draft: CourseDraft) -> None:
    subgraph = build_authoring_subgraph(
        StubLessonReviser(_grounded_author, _unused_revise), _marker_verifier(), draft
    )
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})


async def test_finalize_awaits_and_stitches_a_ready_video_into_its_lesson(tmp_path: Path) -> None:
    # Arrange — author + enqueue, then start a worker draining concurrently (the job is NOT done yet
    # when finalize is called, so this proves finalize BLOCKS on it).
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    # poll_s tiny so finalize enters its poll loop and re-polls — observing the job go QUEUED →
    # READY as the worker drains during the sleep (proving it BLOCKS, not reads a done one).
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01
    )
    draft = _draft_with_graph(coordinator)
    await _author_and_enqueue(draft)
    worker = VideoWorker(
        queue=queue, pipeline=StubVideoPipeline(), storage=storage, events=events, worker_id="w"
    )
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act — finalize and a single worker drain race; finalize's await must wait for the job.
    await asyncio.gather(finalize.ainvoke({}), worker.run_once())

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
    coordinator = QueueVideoBuildCoordinator(queue=queue, storage=storage, owner_id=_OWNER)
    draft = _draft_with_graph(coordinator)
    await _author_and_enqueue(draft)
    worker = VideoWorker(
        queue=queue, pipeline=_FailingPipeline(), storage=storage, events=events, worker_id="w"
    )
    await worker.run_once()  # settles the job FAILED before finalize awaits it
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act — the failed video must NOT block the course.
    result = await finalize.ainvoke({})

    # Assert — the course still finalized; the lesson carries a FAILED (retry-state) video that, as
    # a video that never planned a contract, carries no provenance.
    assert result["courseId"] == "c1"
    lesson = draft.course.modules[0].lessons[0]
    assert lesson.video is not None
    assert lesson.video.status is VideoJobStatus.FAILED
    assert lesson.video.provenance is None


class _FailingPipeline:
    """A pipeline whose produce always raises — to prove finalize degrades, never blocks."""

    async def produce(self, job: VideoJob) -> RenderedVideo:
        raise RuntimeError("render exploded")
