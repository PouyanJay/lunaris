"""P2 T3: the author→verify→revise→triage loop as a deterministic LangGraph sub-graph.

Driven with NO key by a scripted ``StubLessonReviser`` and a stub verifier that grounds only claims
containing the marker word. The tests pin the loop's contract: it revises until claims are grounded,
stops early when a round stops shrinking the cut set, respects the risk-tiered round cap, and flags
a course for review when a goal-critical claim cannot be grounded within budget.
"""

from collections.abc import Sequence

import structlog
from langchain_core.messages import HumanMessage
from lunaris_agent.harness.agent_reporter import AgentReporter
from lunaris_agent.harness.authoring import build_authoring_subgraph
from lunaris_agent.harness.authoring.stub_reviser import StubLessonReviser
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.progress_reporter import ProgressReporter
from lunaris_agent.harness.stage_cursor import StageCursor
from lunaris_agent.lesson_claims import iter_claims
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.schema import (
    AgentEvent,
    AgentEventKind,
    Citation,
    Module,
    ProgressStage,
    RiskTier,
    VerifierStatus,
)

_GROUNDED = "grounded"  # the stub retriever finds evidence only for claims containing this word


class _RecordingAgentSink:
    """An IAgentSink that captures the loop's fine-grained transcript beats for assertion."""

    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    async def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


def _lesson_with_claim(text: str) -> LessonDraft:
    return LessonDraft(
        activate=SegmentDraft("Recall.", []),
        demonstrate=SegmentDraft("Example.", [text]),
        apply=SegmentDraft("Apply.", []),
        integrate=SegmentDraft("Integrate.", []),
    )


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


def _draft(*modules: Module, risk_tier: RiskTier = RiskTier.LOW, goal: str = "c") -> CourseDraft:
    draft = CourseDraft(topic="t", course_id="c1", run_id="r1", risk_tier=risk_tier)
    draft.goal_concept = goal
    draft.modules = list(modules)
    return draft


def _all_claims(draft: CourseDraft) -> list[object]:
    return [
        claim
        for module in draft.modules
        for lesson in module.lessons
        for claim in iter_claims([lesson])
    ]


async def test_loop_revises_until_every_claim_is_grounded() -> None:
    # Arrange — author first emits an unsupported claim; the first revision grounds it.
    draft = _draft(Module(id="m0", title="C", kcs=["c"], difficulty_index=0.5))
    revise_calls: list[int] = []

    def author_fn(module: Module) -> LessonDraft:
        return _lesson_with_claim(f"unsupported fact about {module.title}")

    def revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
        revise_calls.append(attempt)
        return _lesson_with_claim(f"{_GROUNDED} fact about {module.title}")

    subgraph = build_authoring_subgraph(
        StubLessonReviser(author_fn, revise_fn), _marker_verifier(), draft
    )

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author all modules")]})

    # Assert — one revision happened, every claim is now SUPPORTED, nothing was flagged.
    assert revise_calls == [1]
    claims = _all_claims(draft)
    assert claims
    assert all(c.verifier_status is VerifierStatus.SUPPORTED for c in claims)
    assert draft.provenance
    assert draft.needs_review is False


async def test_loop_surfaces_per_module_authoring_and_verify_beats() -> None:
    # Arrange — a recording agent sink + a shared stage cursor advanced by the progress reporter,
    # exactly as the runner wires them, so we can assert the beats bucket into the right phase.
    draft = _draft(Module(id="m0", title="Routing", kcs=["c"], difficulty_index=0.5))
    cursor = StageCursor()
    sink = _RecordingAgentSink()
    draft.progress = ProgressReporter("r1", cursor=cursor)
    draft.agent = AgentReporter("r1", sink, cursor=cursor)

    def author_fn(module: Module) -> LessonDraft:
        return _lesson_with_claim(f"{_GROUNDED} fact about {module.title}")

    def revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
        return _lesson_with_claim("unused")

    subgraph = build_authoring_subgraph(
        StubLessonReviser(author_fn, revise_fn), _marker_verifier(), draft
    )

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — the otherwise-opaque subagent narrated authoring the module and the verify tally, and
    # each beat is stamped with the phase active when it fired (so the live timeline buckets them
    # into Lessons + Verify rather than showing a lone "running…" task).
    authored = next(e for e in sink.events if "Routing" in (e.text or ""))
    assert authored.kind is AgentEventKind.REASONING
    assert authored.stage is ProgressStage.MODULE_AUTHORED
    verified = next(e for e in sink.events if "supported" in (e.text or ""))
    assert verified.stage is ProgressStage.CLAIMS_VERIFIED


async def test_loop_stops_early_when_a_round_stops_shrinking_the_cut_set() -> None:
    # Arrange — high risk (cap 3), but revision never grounds the claim, so the cut set never
    # shrinks; the loop must stop after a single wasted revision rather than burning the budget.
    draft = _draft(
        Module(id="m0", title="C", kcs=["c"], difficulty_index=0.5), risk_tier=RiskTier.HIGH
    )
    revise_calls: list[int] = []

    def author_fn(module: Module) -> LessonDraft:
        return _lesson_with_claim("ungroundable claim one")

    def revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
        revise_calls.append(attempt)
        return _lesson_with_claim("ungroundable claim two")  # still 1 cut → no progress

    subgraph = build_authoring_subgraph(
        StubLessonReviser(author_fn, revise_fn), _marker_verifier(), draft
    )

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — exactly one revision (no-progress early-stop), residual cut, goal-critical → flagged.
    assert revise_calls == [1]
    claims = _all_claims(draft)
    assert all(c.verifier_status is VerifierStatus.CUT for c in claims)
    assert draft.needs_review is True


async def test_low_risk_tier_cap_stops_a_still_improving_loop() -> None:
    # Arrange — low risk (cap 1) on a non-goal-critical module that authors TWO ungroundable claims.
    # Each revision grounds one more, so the cut set keeps SHRINKING (2 → 1) — the convergence guard
    # would NOT stop it. Only the risk-tier cap can stop it after a single revision, so this test
    # fails if _REVISE_CAP[LOW] is wrong (unlike a no-progress loop, where convergence also stops).
    draft = _draft(Module(id="m0", title="A", kcs=["a"], difficulty_index=0.1), goal="c")
    revise_calls: list[int] = []

    # NB: avoid the substring "grounded" in ungroundable claims ("ungrounded" contains the marker).
    def author_fn(module: Module) -> LessonDraft:
        # Two claims, both initially ungroundable (neither contains the marker word).
        return LessonDraft(
            activate=SegmentDraft("Recall.", []),
            demonstrate=SegmentDraft(
                "Example.", ["claim one unsupported", "claim two unsupported"]
            ),
            apply=SegmentDraft("Apply.", []),
            integrate=SegmentDraft("Integrate.", []),
        )

    def revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
        revise_calls.append(attempt)
        # Ground the first claim, leave the second cut → cut set shrinks 2 → 1 (real progress).
        return LessonDraft(
            activate=SegmentDraft("Recall.", []),
            demonstrate=SegmentDraft(
                "Example.", [f"{_GROUNDED} claim one", "claim two unsupported"]
            ),
            apply=SegmentDraft("Apply.", []),
            integrate=SegmentDraft("Integrate.", []),
        )

    subgraph = build_authoring_subgraph(
        StubLessonReviser(author_fn, revise_fn), _marker_verifier(), draft
    )

    # Act
    with structlog.testing.capture_logs() as logs:
        await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — making progress, yet the LOW cap stopped it after exactly one revision; the residual
    # cut on a non-goal module is not flagged for review (goal concept "c" is not taught here).
    assert revise_calls == [1]
    assert draft.needs_review is False
    assert any(event.get("event") == "authoring_loop_finished" for event in logs)


async def test_unparseable_revision_keeps_the_lesson_and_finishes_the_run() -> None:
    # Arrange — the author emits an unsupported claim, and EVERY revision attempt fails to
    # parse (a small draft-tier model that never emits a valid four-phase lesson). The loop
    # must keep the authored lesson, triage the still-cut claim, and finish — not crash the
    # run at its last step (the field failure: keyless device builds died after "Revising…").
    draft = _draft(Module(id="m0", title="C", kcs=["c"], difficulty_index=0.5))

    def author_fn(module: Module) -> LessonDraft:
        return _lesson_with_claim(f"unsupported fact about {module.title}")

    def revise_fn(module: Module, cut: Sequence[str], attempt: int) -> LessonDraft:
        raise ValueError("response is not a complete four-phase lesson")

    sink = _RecordingAgentSink()
    draft.agent = AgentReporter("r1", sink)
    draft.progress = ProgressReporter("r1", cursor=StageCursor())
    subgraph = build_authoring_subgraph(
        StubLessonReviser(author_fn, revise_fn), _marker_verifier(), draft
    )

    # Act — must NOT raise.
    await subgraph.ainvoke({"messages": [HumanMessage(content="author all modules")]})

    # Assert — the authored lesson survived (not dropped by the failed revision)…
    claims = _all_claims(draft)
    assert claims, "the failed revision must not erase the authored lesson"
    # …its claim is still CUT (triaged; the publish gate keeps it out of publication)…
    assert all(c.verifier_status is VerifierStatus.CUT for c in claims)
    # …the goal-critical residue flags the course for review rather than failing the build…
    assert draft.needs_review is True
    # …and the degradation is narrated on the agent channel, not silent.
    reasoning = [e.text for e in sink.events if e.kind is AgentEventKind.REASONING and e.text]
    assert any("keeping the previous lesson" in text for text in reasoning)
