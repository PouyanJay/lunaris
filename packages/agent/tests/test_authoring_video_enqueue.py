"""Video V4-T0: the author→verify→revise loop enqueues a lesson-video job the moment a module
clears verification, and tracks the job id on the draft — the enqueue seam that makes the build's
video generation blocking-but-overlapped (plan §0 / §V4-T0).

Driven with NO key by the same scripted ``StubLessonReviser`` + marker verifier as
``test_authoring_loop`` (a claim is grounded iff it contains the marker word), over a real
``InMemoryVideoJobQueue`` through the real ``QueueVideoBuildCoordinator``. Gating is presence: a
draft with no coordinator (video off) enqueues zero jobs.
"""

from collections.abc import Sequence

from langchain_core.messages import HumanMessage
from lunaris_agent.harness.authoring import build_authoring_subgraph
from lunaris_agent.harness.authoring.stub_reviser import StubLessonReviser
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.persistence import InMemoryVideoJobQueue, InMemoryVideoStorage
from lunaris_runtime.schema import Citation, Module, RiskTier, VideoJobStatus, VideoKind
from lunaris_runtime.video_build import QueueVideoBuildCoordinator

_GROUNDED = "grounded"  # the stub retriever finds evidence only for claims containing this word
_OWNER = "user-a"


def _marker_verifier() -> Verifier:
    """Grounds (SUPPORTED) only claims containing ``_GROUNDED``; everything else is CUT."""
    retriever = StubEvidenceRetriever(
        lambda claim: (
            [
                Evidence(
                    citation=Citation(id=f"src::{claim[:16]}", title="Ref", snippet=claim),
                    score=0.9,
                )
            ]
            if _GROUNDED in claim
            else []
        )
    )
    return Verifier(retriever, StubSupportAssessor())


def _lesson_with_claim(text: str) -> LessonDraft:
    return LessonDraft(
        activate=SegmentDraft("Recall.", []),
        demonstrate=SegmentDraft("Example.", [text]),
        apply=SegmentDraft("Apply.", []),
        integrate=SegmentDraft("Integrate.", []),
    )


def _draft(*modules: Module, risk_tier: RiskTier = RiskTier.LOW) -> CourseDraft:
    draft = CourseDraft(topic="t", course_id="c1", run_id="r1", risk_tier=risk_tier)
    draft.modules = list(modules)
    return draft


def _grounded_author(module: Module) -> LessonDraft:
    return _lesson_with_claim(f"{_GROUNDED} fact about {module.title}")


def _unused_revise(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
    return _lesson_with_claim("unused")


async def test_clean_module_enqueues_one_lesson_job_tracked_on_the_draft() -> None:
    # Arrange — one module that authors a groundable claim (clears verify on round 0).
    queue = InMemoryVideoJobQueue()
    draft = _draft(Module(id="m0", title="Routing", kcs=["c"], difficulty_index=0.5))
    draft.video_coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=InMemoryVideoStorage(), owner_id=_OWNER
    )
    subgraph = build_authoring_subgraph(
        StubLessonReviser(_grounded_author, _unused_revise), _marker_verifier(), draft
    )

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — the lesson's video job was enqueued + tracked on the draft (owner/kind/coords right).
    lesson_id = draft.modules[0].lessons[0].id
    assert lesson_id in draft.enqueued_video_jobs
    job = await queue.get(job_id=draft.enqueued_video_jobs[lesson_id], owner_id=_OWNER)
    assert job is not None
    assert job.kind is VideoKind.LESSON
    assert job.lesson_id == lesson_id
    assert job.course_id == "c1"
    assert job.user_id == _OWNER
    assert job.status is VideoJobStatus.QUEUED


async def test_no_coordinator_enqueues_zero_jobs() -> None:
    # Arrange — video off (no coordinator on the draft).
    queue = InMemoryVideoJobQueue()
    draft = _draft(Module(id="m0", title="Routing", kcs=["c"], difficulty_index=0.5))
    subgraph = build_authoring_subgraph(
        StubLessonReviser(_grounded_author, _unused_revise), _marker_verifier(), draft
    )

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — nothing tracked, nothing claimable.
    assert draft.enqueued_video_jobs == {}
    assert await queue.claim(worker_id="w") is None


async def test_every_module_enqueues_exactly_one_job_across_revise_rounds() -> None:
    # Arrange — module A clears round 0; module B is cut, revised, then clears round 1. Both end
    # with exactly one job (no double-enqueue of A across the second verify), proving per-build
    # dedup + that a module enqueues the moment IT clears, not when the whole loop ends (overlap).
    queue = InMemoryVideoJobQueue()
    draft = _draft(
        Module(id="ma", title="A", kcs=["a"], difficulty_index=0.1),
        Module(id="mb", title="B", kcs=["b"], difficulty_index=0.2),
    )
    draft.video_coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=InMemoryVideoStorage(), owner_id=_OWNER
    )

    def author_fn(module: Module) -> LessonDraft:
        # A is groundable immediately; B is not (needs a revise round).
        grounded = _GROUNDED if module.id == "ma" else "unsupported"
        return _lesson_with_claim(f"{grounded} fact about {module.title}")

    def revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
        return _lesson_with_claim(f"{_GROUNDED} fact about {module.title}")

    subgraph = build_authoring_subgraph(
        StubLessonReviser(author_fn, revise_fn), _marker_verifier(), draft
    )

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — exactly two jobs, one per lesson, distinct ids.
    assert len(draft.enqueued_video_jobs) == 2
    assert len(set(draft.enqueued_video_jobs.values())) == 2
    for module in draft.modules:
        lesson_id = module.lessons[0].id
        assert lesson_id in draft.enqueued_video_jobs


async def test_module_with_residual_cut_still_enqueues_at_triage() -> None:
    # Arrange — the claim is never groundable, so the module reaches triage still cut. Its lesson is
    # final there (won't be revised again) and the video grounds against whatever survived, so it
    # still enqueues — a publishable lesson always gets its video job.
    queue = InMemoryVideoJobQueue()
    draft = _draft(Module(id="m0", title="C", kcs=["c"], difficulty_index=0.5))
    draft.video_coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=InMemoryVideoStorage(), owner_id=_OWNER
    )

    def author_fn(module: Module) -> LessonDraft:
        return _lesson_with_claim("ungroundable one")

    def revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
        return _lesson_with_claim("ungroundable two")

    subgraph = build_authoring_subgraph(
        StubLessonReviser(author_fn, revise_fn), _marker_verifier(), draft
    )

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — the lesson still got a video job despite its residual cut claim.
    lesson_id = draft.modules[0].lessons[0].id
    assert lesson_id in draft.enqueued_video_jobs
