"""Video V4 (cloud-worker ordering fix): the author→verify→revise loop NO LONGER enqueues lesson
videos. The cloud worker renders a lesson video by loading the course from the store, so the course
must be persisted first — which only happens at finalize. Enqueuing therefore moved out of authoring
into ``finalize_course`` (after the persist); see ``test_finalize_video_stitch``. This file pins the
authoring half of that contract: authoring leaves ``enqueued_video_jobs`` empty and the queue idle,
whether or not a coordinator is wired.

Driven with NO key by the same scripted ``StubLessonReviser`` + marker verifier as
``test_authoring_loop`` (a claim is grounded iff it contains the marker word).
"""

from collections.abc import Sequence

from langchain_core.messages import HumanMessage
from lunaris_agent.harness.authoring import build_authoring_subgraph
from lunaris_agent.harness.authoring.stub_reviser import StubLessonReviser
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.persistence import InMemoryVideoJobQueue, InMemoryVideoStorage
from lunaris_runtime.schema import Citation, Module, RiskTier
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


async def test_authoring_does_not_enqueue_lesson_videos() -> None:
    # Arrange — a coordinator IS wired, and a module authors a groundable claim (clears verify).
    # Even so, authoring must not enqueue: the cloud worker needs the persisted course, which only
    # exists after finalize, so the enqueue moved there (the "course not found" ordering fix).
    queue = InMemoryVideoJobQueue()
    draft = _draft(Module(id="m0", title="Routing", kcs=["c"], difficulty_index=0.5))
    draft.video_coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=InMemoryVideoStorage(), owner_id=_OWNER
    )
    subgraph = build_authoring_subgraph(
        StubLessonReviser(_grounded_author, _unused_revise), _marker_verifier(), draft
    )

    # Act — author the module to completion.
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — the lesson was authored, but NO video job was enqueued during authoring; the queue is
    # idle (a worker would claim nothing). Enqueuing is finalize's job now.
    assert draft.modules[0].lessons  # the lesson was authored
    assert draft.enqueued_video_jobs == {}
    assert await queue.claim(worker_id="w") is None


async def test_authoring_enqueues_nothing_across_revise_rounds() -> None:
    # Arrange — module A clears round 0; module B is cut, revised, then clears round 1. Across both
    # rounds authoring still enqueues nothing (the dedup/overlap enqueue is gone entirely).
    queue = InMemoryVideoJobQueue()
    draft = _draft(
        Module(id="ma", title="A", kcs=["a"], difficulty_index=0.1),
        Module(id="mb", title="B", kcs=["b"], difficulty_index=0.2),
    )
    draft.video_coordinator = QueueVideoBuildCoordinator(
        queue=queue, storage=InMemoryVideoStorage(), owner_id=_OWNER
    )

    def author_fn(module: Module) -> LessonDraft:
        grounded = _GROUNDED if module.id == "ma" else "unsupported"
        return _lesson_with_claim(f"{grounded} fact about {module.title}")

    def revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
        return _lesson_with_claim(f"{_GROUNDED} fact about {module.title}")

    subgraph = build_authoring_subgraph(
        StubLessonReviser(author_fn, revise_fn), _marker_verifier(), draft
    )

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — both modules authored, still nothing enqueued.
    assert all(module.lessons for module in draft.modules)
    assert draft.enqueued_video_jobs == {}
    assert await queue.claim(worker_id="w") is None


async def test_no_coordinator_enqueues_zero_jobs() -> None:
    # Arrange — video off (no coordinator on the draft) — the keyless / video-off gate.
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
