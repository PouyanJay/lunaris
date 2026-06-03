"""P2 T7 — parity / DoD eval + variant coverage for the agent-built course.

The final journey task: prove the REAL deep-agent harness (no key) produces a course that passes the
project's Definition of Done — the same independent ``lunaris-eval`` checks the MVP is measured by
(prerequisite order + factuality) — and that the deterministic moats hold across variants:
the prereq tool stays acyclic even when the agent proposes a cycle, and the publish gate withholds
PUBLISHED when claims cannot be grounded. This is the end-to-end guarantee that "a real agent builds
a real course" is true, not just that the wiring runs.
"""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from lunaris_agent.harness.authoring import StubLessonReviser
from lunaris_agent.harness.runner import AgentCourseBuilder
from lunaris_agent.subagents.concept_extractor import Extraction, StubConceptExtractor
from lunaris_agent.subagents.curriculum_architect import (
    CurriculumPlan,
    ModulePlan,
    ObjectivePlan,
    StubCurriculumArchitect,
)
from lunaris_agent.subagents.goal_interpreter import StubGoalInterpreter
from lunaris_agent.subagents.learner_profiler import LearnerProfile, StubLearnerProfiler
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_agent.subagents.resource_curator import StubResourceCurator
from lunaris_agent.subagents.standard_researcher import StubStandardResearcher
from lunaris_eval import evaluate_course
from lunaris_eval.report import CheckResult, EvalReport
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    BloomLevel,
    Citation,
    Course,
    CourseBrief,
    CourseStatus,
    KnowledgeComponent,
    Module,
)

# A stub brief for the agent's new interpret stage; these eval tests assert on the moats/DoD, not
# the brief, so a minimal interpretation suffices (the scripted plan drives the build either way).
_BRIEF = CourseBrief(subject="Binary search", goal="Learn binary search")

# A small but non-trivial topology: two roots feed the terminal goal, so the DoD's fit + prereq
# checks are meaningful (a novice starts at a root; the goal is the final terminal concept).
#   comparison(0.1) ─┐
#                     ├─▶ binary_search(0.7)   [goal]
#   arrays(0.2) ──────┘   sorted_order(0.4) ──▶ binary_search
_GOAL = "binary_search"
_SPECS = [
    ("comparison", "Comparison", 0.1),
    ("arrays", "Arrays", 0.2),
    ("sorted_order", "Sorted Order", 0.4),
    (_GOAL, "Binary Search", 0.7),
]
_EDGES = [("comparison", "sorted_order"), ("sorted_order", _GOAL), ("arrays", _GOAL)]


def _kcs() -> list[KnowledgeComponent]:
    return [
        KnowledgeComponent(
            id=i,
            label=lbl,
            definition=f"What {lbl} means.",
            difficulty=d,
            bloom_ceiling=BloomLevel.APPLY,
        )
        for i, lbl, d in _SPECS
    ]


def _concept_args() -> list[dict[str, object]]:
    return [{"id": i, "label": lbl, "difficulty": d} for i, lbl, d in _SPECS]


def _plan() -> CurriculumPlan:
    # One module per concept, in ascending difficulty (the assembler enforces non-decreasing).
    return CurriculumPlan(
        modules=[
            ModulePlan(
                title=lbl,
                kcs=[i],
                objectives=[
                    ObjectivePlan(
                        kc=i,
                        statement=f"Apply {lbl}.",
                        bloom_level=BloomLevel.APPLY,
                        item_prompts=["q"],
                    )
                ],
            )
            for i, lbl, _ in _SPECS
        ]
    )


def _lesson(module: Module) -> LessonDraft:
    return LessonDraft(
        activate=SegmentDraft("Recall.", []),
        demonstrate=SegmentDraft("Example.", [f"{module.title} narrows the search space."]),
        apply=SegmentDraft("Apply.", []),
        integrate=SegmentDraft("Integrate.", []),
    )


def _report_detail(report: EvalReport) -> str:
    """A readable per-check summary for assertion messages (EvalReport has no summary method)."""
    return "; ".join(f"{c.name}={'ok' if c.passed else 'FAIL'} ({c.detail})" for c in report.checks)


def _check(report: EvalReport, name: str) -> CheckResult | None:
    """The named check, or None if the eval did not emit it (so a missing check fails the assert
    with a readable message instead of a StopIteration error)."""
    return next((c for c in report.checks if c.name == name), None)


def _grounding_verifier(marker: str | None = None) -> Verifier:
    """Grounds claims containing ``marker`` (every claim when ``marker`` is None)."""

    def evidence(claim: str) -> list[Evidence]:
        if marker is not None and marker not in claim:
            return []
        citation = Citation(id=f"src::{claim[:24]}", snippet=claim)
        return [Evidence(citation=citation, score=0.9)]

    return Verifier(StubEvidenceRetriever(evidence), StubSupportAssessor())


def _script(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    concepts: list[dict[str, object]],
    goal: str,
) -> object:
    """The standard agent plan: extract → graph → curriculum → delegate authoring → finalize."""
    return scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "extract_concepts", "args": {"topic": "x"}, "id": "1"}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "build_prerequisite_graph",
                        "args": {"concepts": concepts, "goal": goal},
                        "id": "2",
                    }
                ],
            ),
            AIMessage(
                content="", tool_calls=[{"name": "design_curriculum", "args": {}, "id": "3"}]
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "Author + verify.",
                            "subagent_type": "module-author",
                        },
                        "id": "4",
                    }
                ],
            ),
            AIMessage(content="", tool_calls=[{"name": "finalize_course", "args": {}, "id": "5"}]),
            AIMessage(content="Done."),
        ]
    )


async def _build(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    store: CourseStore,
    *,
    edges: list[tuple[str, str]] | None = None,
    verifier: Verifier | None = None,
) -> Course:
    builder = AgentCourseBuilder(
        _script(scripted_model, _concept_args(), _GOAL),
        store,
        interpreter=StubGoalInterpreter(_BRIEF),
        profiler=StubLearnerProfiler(LearnerProfile(frontier=[])),
        researcher=StubStandardResearcher(),
        extractor=StubConceptExtractor(Extraction(kcs=_kcs(), goal_id=_GOAL)),
        builder=PrerequisiteGraphBuilder(StubPrereqJudge(edges if edges is not None else _EDGES)),
        architect=StubCurriculumArchitect(_plan()),
        reviser=StubLessonReviser(_lesson, lambda m, _c, _a: _lesson(m)),
        curator=StubResourceCurator(),
        verifier=verifier or _grounding_verifier(),
    )
    return await builder.run("binary search", course_id="c-eval", run_id="r-eval")


async def test_agent_built_course_meets_the_definition_of_done(
    scripted_model: Callable[[Sequence[BaseMessage]], object], tmp_path
) -> None:
    # Act — the real harness builds the course; the independent eval scores it.
    course = await _build(scripted_model, CourseStore(tmp_path))
    report = evaluate_course(course)

    # Assert — the DoD (prereq-order + factuality) holds on agent-built output, as it does for the
    # orchestrator. meets_dod is non-vacuous: both checks ran and passed.
    assert report.meets_dod, _report_detail(report)
    assert report.passed, _report_detail(report)
    assert course.status is CourseStatus.PUBLISHED


async def test_prereq_moat_holds_even_when_the_agent_proposes_a_cycle(
    scripted_model: Callable[[Sequence[BaseMessage]], object], tmp_path
) -> None:
    # Arrange — a judge that returns a CYCLE (goal → comparison closes the loop). The agent has no
    # say in ordering; the deterministic builder must still emit an acyclic graph, and the DoD's
    # prerequisite-order check (an independent re-derivation) must still pass.
    cyclic = [*_EDGES, (_GOAL, "comparison")]

    # Act
    course = await _build(scripted_model, CourseStore(tmp_path), edges=cyclic)
    report = evaluate_course(course)

    # Assert — Failure-A held: acyclic graph + DoD prereq order satisfied despite the bad proposal.
    assert course.graph.is_acyclic is True
    prereq = _check(report, "prereq_order")
    assert prereq is not None and prereq.passed, _report_detail(report)


async def test_publish_gate_withholds_when_no_claim_can_be_grounded(
    scripted_model: Callable[[Sequence[BaseMessage]], object], tmp_path
) -> None:
    # Arrange — nothing grounds (marker never present). Every claim is CUT; the goal module's claim
    # is goal-critical, so the course must be REVIEW, not PUBLISHED — yet still factually safe.
    course = await _build(
        scripted_model, CourseStore(tmp_path), verifier=_grounding_verifier(marker="never")
    )
    report = evaluate_course(course)

    # Assert — withheld from publication, but no unsupported claim ships, so factuality still holds.
    assert course.status is CourseStatus.REVIEW
    factuality = _check(report, "factuality")
    assert factuality is not None and factuality.passed, _report_detail(report)


@pytest.mark.parametrize("risk", ["low", "high"])
async def test_agent_course_meets_dod_across_risk_tiers(
    scripted_model: Callable[[Sequence[BaseMessage]], object], tmp_path: Path, risk: str
) -> None:
    # The DoD holds regardless of the revise-budget tier (low=1 round, high=up to 3); with a
    # fully-grounding verifier no revision is needed, but the build must pass the DoD either way.
    from lunaris_runtime.schema import RiskTier

    builder = AgentCourseBuilder(
        _script(scripted_model, _concept_args(), _GOAL),
        CourseStore(tmp_path),
        interpreter=StubGoalInterpreter(_BRIEF),
        profiler=StubLearnerProfiler(LearnerProfile(frontier=[])),
        researcher=StubStandardResearcher(),
        extractor=StubConceptExtractor(Extraction(kcs=_kcs(), goal_id=_GOAL)),
        builder=PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)),
        architect=StubCurriculumArchitect(_plan()),
        reviser=StubLessonReviser(_lesson, lambda m, _c, _a: _lesson(m)),
        curator=StubResourceCurator(),
        verifier=_grounding_verifier(),
        risk_tier=RiskTier.HIGH if risk == "high" else RiskTier.LOW,
    )
    course = await builder.run("binary search", course_id=f"c-{risk}", run_id=f"r-{risk}")

    assert evaluate_course(course).meets_dod
