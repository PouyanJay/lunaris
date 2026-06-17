"""Video V5 acceptance (T4): one end-to-end build that opens with BOTH course-level videos.

The headline promise (plan §V5 Acceptance): a fresh keyed build's course opens with a SUMMARY
trailer and an OVERVIEW intro. Driven on the real seam: the curriculum-design hook enqueues both
course videos at the start, so they render during the build and are folded READY into
``Course.videos`` at finalize (this test drains them explicitly before finalize to pin that). The
lesson videos, enqueued at finalize, are delivered as generating placeholders the reader's
derive-at-read probe recovers — finalize no longer blocks on any render. The narrow variants
(chaptered → MP4, configurable lengths) are proven in ``test_lesson_video_pipeline``; the gate
(video off ⇒ no course videos) in ``test_course_video_build``.
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
from lunaris_agent.harness.tools.design_curriculum import _enqueue_course_videos
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
    CourseBrief,
    KnowledgeComponent,
    Module,
    PrerequisiteGraph,
    VideoJobStatus,
    VideoKind,
)
from lunaris_runtime.video_build import QueueVideoBuildCoordinator
from lunaris_video import StubVideoPipeline, VideoWorker

_GROUNDED = "grounded"
_OWNER = "user-a"
_TERMINAL = (VideoJobStatus.READY, VideoJobStatus.FAILED)


def _marker_verifier() -> Verifier:
    retriever = StubEvidenceRetriever(
        lambda claim: (
            [Evidence(citation=Citation(id=f"s::{claim[:8]}", title="R", snippet=claim), score=0.9)]
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


def _revise_to_grounded(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
    # Every module grounds on round 0, so revise is never reached; if it ever were, it grounds too.
    return _grounded_author(module)


def _draft(coordinator: QueueVideoBuildCoordinator) -> CourseDraft:
    draft = CourseDraft(topic="Algorithms", course_id="c1", run_id="r1")
    draft.modules = [
        Module(id="ma", title="Sorting", kcs=["a"], difficulty_index=0.1),
        Module(id="mb", title="Searching", kcs=["b"], difficulty_index=0.2),
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
            for kc in ("a", "b")
        ],
        edges=[],
        frontier=[],
        is_acyclic=True,
        topo_order=["a", "b"],
    )
    draft.brief = CourseBrief(subject="Algorithms", goal="reason about cost")
    draft.video_coordinator = coordinator
    return draft


async def test_a_fresh_build_opens_with_both_course_level_videos(tmp_path: Path) -> None:
    # Arrange — the coordinator + two workers over one shared queue (the V5 build shape).
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=storage, owner_id=_OWNER, poll_s=0.01
    )
    draft = _draft(coordinator)
    workers = [
        VideoWorker(
            queue=queue,
            pipeline=StubVideoPipeline(),
            storage=storage,
            events=events,
            worker_id=f"w{n}",
        )
        for n in range(2)
    ]
    subgraph = build_authoring_subgraph(
        StubLessonReviser(_grounded_author, _revise_to_grounded), _marker_verifier(), draft
    )
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act — the curriculum-design hook enqueues both course videos; author the lessons; DRAIN the
    # two workers until the course videos finish (they render during the build, BEFORE finalize);
    # finalize (non-blocking) folds the finished course videos into Course.videos and the
    # just-enqueued lesson videos as generating placeholders.
    async with asyncio.timeout(20):
        await _enqueue_course_videos(draft)
        await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})
        while True:
            await asyncio.gather(*(worker.run_once() for worker in workers))
            course_jobs = [
                job
                for job in await queue.list_for_course(course_id="c1", owner_id=_OWNER)
                if job.lesson_id is None
            ]
            if len(course_jobs) == 2 and all(job.status in _TERMINAL for job in course_jobs):
                break
        result = await finalize.ainvoke({})

    # Assert — the course PUBLISHED and OPENS with both course-level videos (exactly those two kinds
    # enqueued), folded READY because they finished before finalize (provenance traces job + kind).
    assert result["courseId"] == "c1"
    assert set(draft.enqueued_course_videos) == {VideoKind.SUMMARY, VideoKind.OVERVIEW}
    videos = draft.course.videos
    assert videos is not None
    assert videos.summary is not None and videos.summary.status is VideoJobStatus.READY
    assert videos.summary.kind is VideoKind.SUMMARY
    assert videos.summary.provenance.job_id == draft.enqueued_course_videos[VideoKind.SUMMARY]
    assert videos.overview is not None and videos.overview.status is VideoJobStatus.READY
    assert videos.overview.kind is VideoKind.OVERVIEW
    assert videos.overview.provenance.job_id == draft.enqueued_course_videos[VideoKind.OVERVIEW]

    # …and the lesson videos, enqueued at finalize, are delivered as generating placeholders (FAILED
    # + job_id, no provenance) the reader's derive-at-read probe recovers as each renders async — so
    # the course-level pair and the per-lesson heroes coexist (the full V5 reader surface).
    for module in draft.course.modules:
        video = module.lessons[0].video
        assert video is not None, f"module {module.id} has no lesson video"
        assert video.status is VideoJobStatus.FAILED and video.job_id, f"not a placeholder: {video}"
        assert video.provenance is None
