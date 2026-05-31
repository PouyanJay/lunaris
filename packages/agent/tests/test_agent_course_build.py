"""P2 end-to-end: the REAL deep-agent harness builds + persists a full course with NO API key.

A scripted model drives the whole pipeline — extract → prerequisite graph (moat) → curriculum →
delegate to the module-author subagent (author → verify → revise loop) → finalize — proving every
layer is wired (harness → tools → moats → subagent → finalize → store), that provenance flows from
the verifier onto the course, and that the ``run_id`` threads the structured logs. Plus a guard test
that finalize refuses to assemble a course before the prerequisite graph exists.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
import structlog
from langchain_core.messages import AIMessage, BaseMessage
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.authoring import StubLessonReviser
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.runner import AgentCourseBuilder
from lunaris_agent.harness.tools import make_finalize_course_tool
from lunaris_agent.lesson_claims import iter_claims
from lunaris_agent.subagents.concept_extractor import Extraction, StubConceptExtractor
from lunaris_agent.subagents.curriculum_architect import (
    CurriculumPlan,
    ModulePlan,
    ObjectivePlan,
    StubCurriculumArchitect,
)
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    BloomLevel,
    Citation,
    CourseStatus,
    KnowledgeComponent,
    Module,
    VerifierStatus,
)

# One source of truth for the fixture: "a" and "b" are independent roots, both prerequisites of
# the goal "c" (mirrors the P1 moat test). _KCS (domain objects the stub extractor returns) and
# _CONCEPT_ARGS (the dict the scripted model passes to the graph tool) are derived from it so they
# can never drift apart.
_GOAL_ID = "c"
_CONCEPT_SPECS = [
    ("a", "A", "first", 0.1),
    ("b", "B", "second", 0.2),
    (_GOAL_ID, "C", "goal", 0.5),
]
_EDGES = [("a", _GOAL_ID), ("b", _GOAL_ID)]
_KCS = [
    KnowledgeComponent(
        id=kc_id,
        label=label,
        definition=definition,
        difficulty=difficulty,
        bloom_ceiling=BloomLevel.APPLY,
    )
    for kc_id, label, definition, difficulty in _CONCEPT_SPECS
]
_CONCEPT_ARGS = [
    {"id": kc_id, "label": label, "definition": definition, "difficulty": difficulty}
    for kc_id, label, definition, difficulty in _CONCEPT_SPECS
]
# One module per concept, ordered by ascending difficulty (the assembler enforces non-decreasing
# difficulty across modules). Each objective is backed by one assessment-item prompt.
_PLAN = CurriculumPlan(
    modules=[
        ModulePlan(
            title=label,
            kcs=[kc_id],
            objectives=[
                ObjectivePlan(
                    kc=kc_id,
                    statement=f"Given a task, the learner can apply {label}.",
                    bloom_level=BloomLevel.APPLY,
                    item_prompts=["q"],
                )
            ],
        )
        for kc_id, label, _definition, _difficulty in _CONCEPT_SPECS
    ]
)


def _lesson_with_claim(text: str) -> LessonDraft:
    """A minimal Merrill lesson whose demonstrate phase carries one factual claim to verify."""
    return LessonDraft(
        activate=SegmentDraft("Recall what you already know.", []),
        demonstrate=SegmentDraft("Worked example.", [text]),
        apply=SegmentDraft("Try it yourself.", []),
        integrate=SegmentDraft("Connect it to the bigger picture.", []),
    )


def _lesson_draft(module: Module) -> LessonDraft:
    """A first-pass lesson carrying a groundable claim (the happy path)."""
    return _lesson_with_claim(f"{module.title} reduces the problem size each step.")


def _verifier(marker: str | None = None) -> Verifier:
    """Stub verifier: grounds claims containing ``marker`` (every claim when ``marker`` is None)."""

    def evidence(claim: str) -> list[Evidence]:
        if marker is not None and marker not in claim:
            return []
        return [
            Evidence(
                citation=Citation(id=f"src::{claim[:24]}", title="Reference", snippet=claim),
                score=0.9,
            )
        ]

    return Verifier(StubEvidenceRetriever(evidence), StubSupportAssessor())


def _reviser() -> StubLessonReviser:
    """A reviser whose first pass authors a groundable lesson; revision repeats it (unused)."""
    return StubLessonReviser(_lesson_draft, lambda module, _cut, _attempt: _lesson_draft(module))


def _builder(
    model: object,
    store: CourseStore,
    *,
    reviser: StubLessonReviser | None = None,
    verifier: Verifier | None = None,
) -> AgentCourseBuilder:
    """Construct the agent course builder over the no-key stub subagents + real moats."""
    return AgentCourseBuilder(
        model,
        store,
        extractor=StubConceptExtractor(Extraction(kcs=_KCS, goal_id=_GOAL_ID)),
        builder=PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)),
        architect=StubCurriculumArchitect(_PLAN),
        reviser=reviser or _reviser(),
        verifier=verifier or _verifier(),
    )


def _delegating_script(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
) -> object:
    """The standard happy-path agent script: extract → graph → curriculum → delegate → finalize."""
    return scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "extract_concepts", "args": {"topic": "demo"}, "id": "t1"}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "build_prerequisite_graph",
                        "args": {"concepts": _CONCEPT_ARGS, "goal": _GOAL_ID},
                        "id": "t2",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "design_curriculum", "args": {}, "id": "t3"}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Author and verify the lessons for all modules.",
                            "subagent_type": "module-author",
                        },
                        "id": "t4",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "finalize_course", "args": {}, "id": "t5"}],
            ),
            AIMessage(content="Course built."),
        ]
    )


def _course_claims(course: object) -> list[object]:
    """Every claim across the course's lessons (one source of truth via iter_claims)."""
    lessons = [lesson for module in course.modules for lesson in module.lessons]
    return list(iter_claims(lessons))


async def test_agent_builds_and_persists_a_course_without_a_key(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — the standard agent script: plan, call the moat tools, delegate authoring, finalize.
    model = _delegating_script(scripted_model)
    store = CourseStore(tmp_path)
    builder = _builder(model, store)

    # Act — include merge_contextvars so the capture reflects what real sinks see (the bound
    # run_id), not just explicit kwargs; capture_logs() otherwise strips that processor.
    with structlog.testing.capture_logs(
        processors=[structlog.contextvars.merge_contextvars]
    ) as logs:
        course = await builder.run("demo", course_id="course-1", run_id="run-1")

    # Assert — the moat held: an acyclic graph with prerequisites before the goal.
    assert course.graph.is_acyclic is True
    topo = course.graph.topo_order
    assert topo.index("a") < topo.index(_GOAL_ID)
    assert topo.index("b") < topo.index(_GOAL_ID)

    # The curriculum tool populated real modules (one per concept, each with a backed objective) —
    # not the graph-fallback. Difficulty is non-decreasing across modules (assembler invariant).
    assert len(course.modules) == len(_CONCEPT_SPECS)
    assert all(module.objectives for module in course.modules)
    difficulties = [module.difficulty_index for module in course.modules]
    assert difficulties == sorted(difficulties)

    # The module-author subagent authored a Merrill lesson per module and its verify→revise loop
    # grounded every claim: supported claims carry a citation, recorded as the course's provenance.
    assert all(module.lessons for module in course.modules)
    all_claims = _course_claims(course)
    assert all_claims  # the lessons did carry factual claims
    assert all(claim.verifier_status is VerifierStatus.SUPPORTED for claim in all_claims)
    # Provenance is coherent, not just non-empty: every supported claim's citation id resolves to
    # a citation actually recorded on the course (provenance constructed at source, flowed through).
    citation_ids = {citation.id for citation in course.provenance}
    assert citation_ids
    assert all(claim.supported_by in citation_ids for claim in all_claims)

    # With every module taught by a verified lesson, the publish gate now passes → PUBLISHED.
    assert course.goal_concept == _GOAL_ID
    assert course.status == CourseStatus.PUBLISHED

    # The course was actually persisted and is retrievable from the store.
    assert store.load("course-1").id == "course-1"

    # run_id threads the logs via contextvars (asserted on run_started, which does NOT pass
    # run_id explicitly — so this proves bind_run_id propagation, not just a hardcoded kwarg).
    assert any(
        event.get("event") == "agent_course_run_started" and event.get("run_id") == "run-1"
        for event in logs
    )


async def test_agent_publishes_after_the_subagent_revises_a_cut_claim(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — through the real task→subagent boundary: the first authored claim is ungroundable,
    # so the module-author loop must REVISE it (the revision grounds it) before the course can ship.
    revisions: list[int] = []

    # The first-pass claim lacks the marker (so it's CUT); the revision adds it (so it grounds).
    # NB: keep the marker substring out of the first-pass text ("ungrounded" contains "grounded").
    def author_fn(module: Module) -> LessonDraft:
        return _lesson_with_claim(f"unsupported fact about {module.title}")

    def revise_fn(module: Module, _cut: Sequence[str], attempt: int) -> LessonDraft:
        revisions.append(attempt)
        return _lesson_with_claim(f"grounded fact about {module.title}")

    builder = _builder(
        _delegating_script(scripted_model),
        CourseStore(tmp_path),
        reviser=StubLessonReviser(author_fn, revise_fn),
        verifier=_verifier(marker="grounded"),  # only the revised claims ground
    )

    # Act
    course = await builder.run("demo", course_id="course-3", run_id="run-3")

    # Assert — the loop actually revised (not a first-pass publish); every claim is now grounded.
    assert revisions  # at least one revision happened inside the delegated subagent
    claims = _course_claims(course)
    assert claims
    assert all(claim.verifier_status is VerifierStatus.SUPPORTED for claim in claims)
    assert course.status == CourseStatus.PUBLISHED


async def test_agent_flags_review_when_a_goal_claim_cannot_be_grounded(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — nothing ever grounds, so the goal-critical module's claim stays cut. The publish
    # gate alone would still pass (cut claims are simply dropped), so this pins the triage path:
    # a goal-critical residual must flag the course for REVIEW rather than PUBLISHED.
    never = StubLessonReviser(
        lambda module: _lesson_with_claim("ungroundable goal claim"),
        lambda module, _cut, _attempt: _lesson_with_claim("still ungroundable"),
    )
    store = CourseStore(tmp_path)
    builder = _builder(
        _delegating_script(scripted_model),
        store,
        reviser=never,
        verifier=_verifier(marker="never-present-marker"),
    )

    # Act
    course = await builder.run("demo", course_id="course-4", run_id="run-4")

    # Assert — withheld from publication, but still assembled + persisted for review.
    assert course.status == CourseStatus.REVIEW
    assert store.load("course-4").status == CourseStatus.REVIEW


async def test_finalize_before_graph_is_rejected(tmp_path: Path) -> None:
    # Arrange — the finalize tool over a draft whose prerequisite graph was never built. The moat
    # must refuse to assemble a course out of order rather than emit a malformed one. Tested
    # directly on the tool (deterministic) rather than through the agent loop, which retries a
    # failed tool call.
    draft = CourseDraft(topic="demo", course_id="course-2", run_id="run-2")
    finalize = make_finalize_course_tool(MinimalCritic(), CourseStore(tmp_path), draft)

    # Act / Assert — the precondition fails loudly, and nothing is persisted.
    with pytest.raises(RuntimeError, match="before the prerequisite"):
        await finalize.ainvoke({})
    assert draft.course is None
    assert not (tmp_path / "course-2.json").exists()
