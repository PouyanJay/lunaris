"""P2 end-to-end: the REAL deep-agent harness builds + persists a full course with NO API key.

A scripted model drives the whole pipeline — extract → prerequisite graph (moat) → curriculum →
delegate to the module-author subagent (author → verify → revise loop) → finalize — proving every
layer is wired (harness → tools → moats → subagent → finalize → store), that provenance flows from
the verifier onto the course, and that the ``run_id`` threads the structured logs. Plus a guard test
that finalize refuses to assemble a course before the prerequisite graph exists.
"""

import json
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
import structlog
from langchain_core.messages import AIMessage, BaseMessage
from lunaris_agent.coverage_critic import (
    DeterministicCoverageCritic,
    ICoverageCritic,
    StubCoverageCritic,
)
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.authoring import StubLessonReviser
from lunaris_agent.harness.discovery import (
    IGroundingDiscoverer,
    RelevanceVerdict,
    StubGroundingDiscoverer,
    SubgraphGroundingDiscoverer,
)
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.event_tap import stream_course_build as real_stream_course_build
from lunaris_agent.harness.runner import AgentCourseBuilder
from lunaris_agent.harness.seeding import GroundingSeeder, IGroundingSeeder, StubGroundingSeeder
from lunaris_agent.harness.tools import make_finalize_course_tool
from lunaris_agent.lesson_claims import iter_claims
from lunaris_agent.subagents.concept_extractor import Extraction, StubConceptExtractor
from lunaris_agent.subagents.curriculum_architect import (
    AssessmentItemPlan,
    CurriculumPlan,
    ModulePlan,
    ObjectivePlan,
    StubCurriculumArchitect,
)
from lunaris_agent.subagents.goal_interpreter import StubGoalInterpreter
from lunaris_agent.subagents.learner_profiler import (
    ILearnerProfiler,
    LearnerProfile,
    StubLearnerProfiler,
)
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_agent.subagents.resource_curator import CuratedResources, StubResourceCurator
from lunaris_agent.subagents.scope_polisher import IScopePolisher
from lunaris_agent.subagents.standard_researcher import SeedSource, StubStandardResearcher
from lunaris_agent.subagents.visual_agent import (
    StubDiagramRenderer,
    StubVisualGenerator,
    VisualEngine,
)
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_grounding import (
    CorpusIngestor,
    CredibilityScorer,
    Evidence,
    ExtractedContent,
    InMemoryCorpusStore,
    InMemorySourceAuthorityStore,
    SearchResult,
    StubContentExtractor,
    StubEmbedder,
    StubEvidenceRetriever,
    StubSearchProvider,
    StubSupportAssessor,
    Verifier,
)
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    AcquisitionMode,
    AgentEventKind,
    BloomLevel,
    Citation,
    Clarification,
    CourseBrief,
    CourseScope,
    CourseStatus,
    GoalType,
    KnowledgeComponent,
    Level,
    Module,
    ProgressStage,
    ResearchSource,
    ResearchStatus,
    Resource,
    ResourceKind,
    StandardResearch,
    TargetStandard,
    TrustTier,
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
                    items=[AssessmentItemPlan("q")],
                )
            ],
        )
        for kc_id, label, _definition, _difficulty in _CONCEPT_SPECS
    ]
)


# The stub interpreter's brief: the new first stage records it on the draft. These tests assert on
# the moats + the brief flowing first, so a small fixed interpretation is enough.
_BRIEF = CourseBrief(
    subject="Demonstrations", goal="Build a demo course", target_level=Level.NOVICE
)

# Small fixed findings: enough to assert stage ordering + provenance flow without a distillation
# path (COMPLETE requires at least one cited source — the schema invariant).
_RESEARCH = StandardResearch(
    status=ResearchStatus.COMPLETE,
    competencies=["hear implied intent in speech", "read authorial stance and subtext"],
    sources=[
        ResearchSource(
            url="https://www.canada.ca/clb-10",
            title="Canadian Language Benchmarks 10",
            trust_tier=TrustTier.OFFICIAL,
            fetched_at="2026-06-03T00:00:00Z",
        )
    ],
)


_COMPETENCY = "hear implied intent and hedged disagreement in speech"
# A competency-tagged plan (P7.3): one module per concept, each mapped to the researched competency.
_ARC_PLAN = CurriculumPlan(
    modules=[
        ModulePlan(
            title=label,
            kcs=[kc_id],
            competency=_COMPETENCY,
            objectives=[
                ObjectivePlan(
                    kc=kc_id,
                    statement=f"Given a task, the learner can apply {label}.",
                    bloom_level=BloomLevel.APPLY,
                    items=[AssessmentItemPlan("q")],
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


def _arc_lesson(module: Module) -> LessonDraft:
    """A lesson draft carrying the arc bookends (P7.3) plus a groundable claim (the happy path)."""
    return LessonDraft(
        activate=SegmentDraft("Recall what you already know.", []),
        demonstrate=SegmentDraft(
            "Worked example.", [f"{module.title} reduces the problem size each step."]
        ),
        apply=SegmentDraft("Try it yourself.", []),
        integrate=SegmentDraft("Connect it to the bigger picture.", []),
        expects=[f"You can already use {module.title}."],
        self_check=[f"Can you apply {module.title} unaided?"],
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
    brief: CourseBrief | None = None,
    profiler: ILearnerProfiler | None = None,
    researcher: StubStandardResearcher | None = None,
    architect: StubCurriculumArchitect | None = None,
    reviser: StubLessonReviser | None = None,
    curator: StubResourceCurator | None = None,
    seeder: IGroundingSeeder | None = None,
    discoverer: IGroundingDiscoverer | None = None,
    verifier: Verifier | None = None,
    coverage_critic: ICoverageCritic | None = None,
    visual_engine: VisualEngine | None = None,
    scope_polisher: IScopePolisher | None = None,
    stream_tokens: bool = False,
) -> AgentCourseBuilder:
    """Construct the agent course builder over the no-key stub subagents + real moats."""
    return AgentCourseBuilder(
        model,
        store,
        interpreter=StubGoalInterpreter(brief or _BRIEF),
        profiler=profiler or StubLearnerProfiler(LearnerProfile(frontier=[])),
        researcher=researcher or StubStandardResearcher(),
        extractor=StubConceptExtractor(Extraction(kcs=_KCS, goal_id=_GOAL_ID)),
        builder=PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)),
        architect=architect or StubCurriculumArchitect(_PLAN),
        reviser=reviser or _reviser(),
        curator=curator or StubResourceCurator(),
        seeder=seeder or StubGroundingSeeder(),
        discoverer=discoverer or StubGroundingDiscoverer(),
        verifier=verifier or _verifier(),
        coverage_critic=coverage_critic,
        visual_engine=visual_engine,
        scope_polisher=scope_polisher,
        stream_tokens=stream_tokens,
    )


def _delegating_script(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    *,
    first_narration: str = "",
) -> object:
    """The standard happy-path agent script: interpret → research → model learner → extract →
    graph → curriculum → seed grounding → discover grounding → delegate → finalize.

    ``first_narration`` lets a test make the agent narrate its first step (text that streams as
    tokens in token mode); it defaults to empty, leaving the deterministic tool-only turns intact.
    """
    return scripted_model(
        [
            AIMessage(
                content=first_narration,
                tool_calls=[{"name": "interpret_request", "args": {"request": "demo"}, "id": "t0"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "research_standard", "args": {}, "id": "t0a"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "model_learner", "args": {}, "id": "t0b"}],
            ),
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
                tool_calls=[{"name": "seed_grounding", "args": {}, "id": "t3z"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "discover_grounding", "args": {}, "id": "t3a"}],
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
                tool_calls=[{"name": "curate_resources", "args": {}, "id": "t5"}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"name": "finalize_course", "args": {}, "id": "t6"}],
            ),
            AIMessage(content="Course built."),
        ]
    )


def _course_claims(course: object) -> list[object]:
    """Every claim across the course's lessons (one source of truth via iter_claims)."""
    lessons = [lesson for module in course.modules for lesson in module.lessons]
    return list(iter_claims(lessons))


class _RecordingProfiler:
    """A learner profiler that captures the brief it is handed, so a test can assert which brief
    (inferred vs. clarification-merged) reached the stage that sharpens the frontier."""

    def __init__(self) -> None:
        self.seen: CourseBrief | None = None

    async def profile(self, brief: CourseBrief) -> LearnerProfile:
        self.seen = brief
        return LearnerProfile(frontier=[])


async def test_clarification_reaches_the_learner_profiler_through_the_full_build(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — the stub interpreter infers NOVICE (_BRIEF); an opt-in clarification confirms a
    # higher level + reports prior knowledge. The profiler records the brief it is handed.
    profiler = _RecordingProfiler()
    builder = _builder(_delegating_script(scripted_model), CourseStore(tmp_path), profiler=profiler)

    # Act
    await builder.run(
        "demo",
        course_id="course-clar",
        run_id="run-clar",
        clarification=Clarification(
            target_level=Level.ADVANCED, assumed_known="the entire beginner ladder"
        ),
    )

    # Assert — the profiler saw the CALIBRATED brief (clarification → interpret merge → draft.brief
    # → model_learner), proving the diagnostic reaches the stage that sharpens the frontier.
    assert profiler.seen is not None
    assert profiler.seen.target_level == Level.ADVANCED
    assert "the entire beginner ladder" in profiler.seen.assumed_prior


async def test_build_without_a_clarification_profiles_the_inferred_brief(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — the default one-click path: no clarification is passed.
    profiler = _RecordingProfiler()
    builder = _builder(_delegating_script(scripted_model), CourseStore(tmp_path), profiler=profiler)

    # Act
    await builder.run("demo", course_id="course-noclar", run_id="run-noclar")

    # Assert — the profiler saw the interpreter's inference verbatim (the stub _BRIEF's NOVICE),
    # i.e. the skip path is byte-for-byte today's inferred-only build.
    assert profiler.seen is not None
    assert profiler.seen.target_level == Level.NOVICE


async def test_goal_type_threads_from_the_brief_to_the_finalized_course(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Walking skeleton (CQ Phase 1): goal_type must thread brief → draft → finalize → Course and
    # survive persistence. CREDENTIAL (non-default) proves the thread, not the field's default.
    # Arrange
    store = CourseStore(tmp_path)
    brief = CourseBrief(
        subject="AWS",
        goal="Pass the AWS Solutions Architect exam",
        target_level=Level.INTERMEDIATE,
        goal_type=GoalType.CREDENTIAL,
    )
    builder = _builder(_delegating_script(scripted_model), store, brief=brief)

    # Act
    course = await builder.run("demo", course_id="course-gt", run_id="run-gt")

    # Assert — the classification reached the finalized course and round-trips through the store.
    assert course.goal_type is GoalType.CREDENTIAL
    assert store.load("course-gt").goal_type is GoalType.CREDENTIAL


async def test_scope_band_threads_from_the_brief_to_the_finalized_course(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Walking skeleton (CQ Phase 3.1): the finalize step computes a scope-realism band from the
    # brief (effort/timeline + what this does / does not get you) and persists it on the course, so
    # the reader can show an honest header band. A non-default goal_type proves the thread.
    # Arrange
    store = CourseStore(tmp_path)
    brief = CourseBrief(
        subject="AWS",
        goal="Pass the AWS Solutions Architect exam",
        target_level=Level.INTERMEDIATE,
        goal_type=GoalType.CREDENTIAL,
    )
    builder = _builder(_delegating_script(scripted_model), store, brief=brief)

    # Act
    course = await builder.run("demo", course_id="course-scope", run_id="run-scope")

    # Assert — a scope band reached the finalized course, the goal_type=CREDENTIAL carried all the
    # way to the excludes content (not just a non-empty field), and it round-trips unchanged.
    assert course.scope is not None
    assert course.scope.effort
    assert course.scope.delivers
    assert "guarantee" in " ".join(course.scope.excludes).lower()
    assert store.load("course-scope").scope == course.scope


class _RewordingPolisher:
    """A well-behaved scope polisher: rewrites the band's lines (preserving their count) while
    keeping the deterministic effort fact — proves the finalize tool actually invokes the injected
    polisher and persists its result. (Drift-discarding is unit-tested on ClaudeScopePolisher.)"""

    async def polish(self, scope: CourseScope, *, brief: CourseBrief | None) -> CourseScope:
        return CourseScope(
            effort=scope.effort,  # a faithful polisher never changes the effort fact
            delivers=[f"POLISHED: {line}" for line in scope.delivers],
            excludes=[f"POLISHED: {line}" for line in scope.excludes],
        )


async def test_scope_band_is_wording_polished_when_a_polisher_is_wired(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Hybrid path (CQ Phase 3.1): with a polisher wired, finalize refines the band's WORDING; the
    # deterministic effort fact is preserved, and the polished band is persisted.
    # Arrange
    store = CourseStore(tmp_path)
    builder = _builder(
        _delegating_script(scripted_model), store, scope_polisher=_RewordingPolisher()
    )

    # Act
    course = await builder.run("demo", course_id="course-polish", run_id="run-polish")

    # Assert — every line was polished, the effort still reads as the deterministic band, and the
    # polished result round-trips through the store.
    assert course.scope is not None
    assert all(line.startswith("POLISHED:") for line in course.scope.delivers)
    assert all(line.startswith("POLISHED:") for line in course.scope.excludes)
    assert "week" in course.scope.effort.lower()  # the deterministic effort, untouched by polish
    assert store.load("course-polish").scope == course.scope


async def test_research_needing_goal_without_grounding_is_scoped_and_withheld(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Honesty gate (CQ Phase 1.6): a goal that needs_research but whose research came back
    # UNAVAILABLE (the stub researcher, no key) must NOT publish as if grounded — it carries an
    # honest scope caveat and is withheld for review.
    # Arrange
    store = CourseStore(tmp_path)
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        needs_research=True,
        target_standard=TargetStandard(name="CLB 10"),
    )
    builder = _builder(_delegating_script(scripted_model), store, brief=brief)

    # Act
    course = await builder.run("demo", course_id="course-honest", run_id="run-honest")

    # Assert — an honest caveat naming the standard, withheld from publication, and it survives
    # persistence (the learner sees the caveat, not a course dressed as grounded).
    assert "CLB 10" in course.scope_note
    assert course.status == CourseStatus.REVIEW
    assert store.load("course-honest").scope_note == course.scope_note


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


async def test_agent_pipeline_carries_the_lesson_arc_and_module_competency(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — the FULL scripted agent loop (not the assemblers directly): a competency-tagged plan
    # and an arc-authoring reviser, so the arc + competency are proven through the real
    # task→subagent→finalize boundary, not just the assembler unit (T0).
    store = CourseStore(tmp_path)
    builder = _builder(
        _delegating_script(scripted_model),
        store,
        architect=StubCurriculumArchitect(_ARC_PLAN),
        reviser=StubLessonReviser(_arc_lesson, lambda module, _cut, _attempt: _arc_lesson(module)),
    )

    # Act
    course = await builder.run("demo", course_id="course-arc", run_id="run-arc")

    # Assert — every module records the competency, and every authored lesson carries both bookends.
    assert course.modules
    assert all(module.competency == _COMPETENCY for module in course.modules)
    for module in course.modules:
        lesson = module.lessons[0]
        assert lesson.expects == [f"You can already use {module.title}."]
        assert lesson.self_check == [f"Can you apply {module.title} unaided?"]

    # The arc + competency survive persistence through the real finalize path, with exact values
    # intact (re-serialization is the most likely place a list field silently drops to []).
    reloaded = store.load("course-arc")
    for module in reloaded.modules:
        assert module.competency == _COMPETENCY
        assert module.lessons[0].expects == [f"You can already use {module.title}."]
        assert module.lessons[0].self_check == [f"Can you apply {module.title} unaided?"]


def _curate_one_video(module: Module) -> CuratedResources:
    """A stub curation: one vetted video on the demonstrate phase of every module's lesson."""
    return CuratedResources(
        demonstrate=[
            Resource(
                kind=ResourceKind.VIDEO,
                title=f"{module.title} explained",
                url=f"https://youtu.be/{module.id}",
                source="youtu.be",
                why=f"A short walkthrough of {module.title}.",
                trust_tier=TrustTier.OPEN,
                credibility=0.8,
                fetched_at="2026-06-03T00:00:00Z",
            )
        ]
    )


async def test_agent_pipeline_curates_resources_onto_lesson_segments(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — the FULL scripted agent loop (the script calls curate_resources after authoring),
    # with a curator attaching one video per module, so the per-phase resources are proven through
    # the real curate_resources tool → finalize → persist path, not just the curator unit test (T1).
    store = CourseStore(tmp_path)
    builder = _builder(
        _delegating_script(scripted_model),
        store,
        curator=StubResourceCurator(_curate_one_video),
    )

    # Act
    course = await builder.run("demo", course_id="course-res", run_id="run-res")

    # Assert — every module's lesson carries its curated video on the demonstrate phase, with the
    # provenance intact, and it survives persistence.
    assert course.modules
    for module in course.modules:
        resources = module.lessons[0].segments.demonstrate.resources
        assert [r.kind for r in resources] == [ResourceKind.VIDEO]
        assert resources[0].url == f"https://youtu.be/{module.id}"
        assert resources[0].why.startswith("A short walkthrough")
    reloaded = store.load("course-res")
    for module in reloaded.modules:
        resources = module.lessons[0].segments.demonstrate.resources
        assert [r.kind for r in resources] == [ResourceKind.VIDEO]
        assert resources[0].url == f"https://youtu.be/{module.id}"
        assert resources[0].why.startswith("A short walkthrough")


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


async def test_agent_pipeline_illustrates_the_authored_lessons(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — the agent builder with a visual engine injected (no key, no render toolchain).
    # This pins the P5 wiring: the deep-agent harness must illustrate the authored lessons the way
    # the legacy Orchestrator does, not silently skip visuals.
    store = CourseStore(tmp_path)
    engine = VisualEngine(StubVisualGenerator(), StubDiagramRenderer())
    builder = _builder(_delegating_script(scripted_model), store, visual_engine=engine)

    # Act
    course = await builder.run("demo", course_id="course-vis", run_id="run-vis")

    # Assert — every authored lesson's demonstrate segment carries a visual, and they survive
    # persistence (proving the engine ran BEFORE finalize assembled + saved the course, not after).
    assert course.modules and all(module.lessons for module in course.modules)
    for module in course.modules:
        for lesson in module.lessons:
            assert lesson.segments.demonstrate.visuals, f"module {module.id} got no visual"
    reloaded = store.load("course-vis")
    for module in reloaded.modules:
        for lesson in module.lessons:
            assert lesson.segments.demonstrate.visuals, f"reloaded {module.id} lost a visual"


async def test_agent_pipeline_ships_without_a_visual_engine(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
) -> None:
    # Arrange — no visual engine wired (the optional dependency is absent).
    store = CourseStore(tmp_path)
    builder = _builder(_delegating_script(scripted_model), store)

    # Act — the build still completes and publishes; visuals are simply absent.
    course = await builder.run("demo", course_id="course-novis", run_id="run-novis")

    # Assert — no visuals, but a valid persisted course (visuals are never a hard dependency).
    assert course.status == CourseStatus.PUBLISHED
    lessons = [lesson for module in course.modules for lesson in module.lessons]
    assert lessons  # guard against a vacuous all() over an empty course
    assert all(not lesson.segments.demonstrate.visuals for lesson in lessons)


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


async def test_agent_builder_emits_transcript_events_to_the_agent_sink(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    agent_sink,
    tmp_path: Path,
) -> None:
    # Arrange — the real AgentCourseBuilder with a recording agent sink (closes the gap the API
    # test masks with its own pipeline: prove the BUILDER itself emits the transcript channel).
    builder = _builder(_delegating_script(scripted_model), CourseStore(tmp_path))
    sink = agent_sink

    # Act
    await builder.run("demo", course_id="course-5", run_id="run-5", agent=sink)

    # Assert — the REAL harness tap produced a rich transcript: reasoning plus each tool's call
    # and result, run_id-correlated and monotonically sequenced. (The scripted plan does not call
    # write_todos, so TODO mapping is covered exhaustively by the event-tap unit tests instead.)
    assert sink.events, "the agent builder emitted no transcript events"
    kinds = {event.kind for event in sink.events}
    assert AgentEventKind.REASONING in kinds
    assert AgentEventKind.TOOL_CALL in kinds
    assert AgentEventKind.TOOL_RESULT in kinds
    assert all(e.run_id == "run-5" for e in sink.events)
    assert [e.sequence for e in sink.events] == list(range(len(sink.events)))
    # The moat tools show up as real tool calls carrying their args.
    tool_calls = [e for e in sink.events if e.kind is AgentEventKind.TOOL_CALL]
    assert any(e.tool == "extract_concepts" and e.tool_args for e in tool_calls)
    # The scripted plan drives the full pipeline, so the tap must surface a named result for each
    # distinct stage tool — not pass vacuously on a low threshold (the new research stage included).
    tool_results = [e for e in sink.events if e.kind is AgentEventKind.TOOL_RESULT]
    assert all(e.tool for e in tool_results)
    result_tools = {e.tool for e in tool_results}
    assert {
        "interpret_request",
        "research_standard",
        "model_learner",
        "extract_concepts",
        "design_curriculum",
        "discover_grounding",
        "finalize_course",
    } <= result_tools


async def test_agent_builder_forwards_stream_tokens_to_the_harness_tap(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The token-by-token path is verified at the tap (test_event_tap), where a controlled
    # multi-mode stream can be replayed. Here we pin the WIRING: a builder constructed with
    # stream_tokens=True forwards that to the harness tap. It can't be exercised through a full
    # scripted build — a GenericFakeChatModel drops its tool_calls when forced to stream, so the
    # agent loop can't reach finalize (the very reason the no-key path stays on ``updates``). So the
    # spy records the forwarded flag, then forwards to the REAL tap in ``updates`` mode, letting the
    # deterministic build complete normally.
    captured: dict[str, bool] = {}

    async def spy(agent: object, inputs: object, reporter: object, *, stream_tokens: bool = False):
        captured["stream_tokens"] = stream_tokens
        await real_stream_course_build(agent, inputs, reporter, stream_tokens=False)  # type: ignore[arg-type]

    monkeypatch.setattr("lunaris_agent.harness.runner.stream_course_build", spy)
    builder = _builder(
        _delegating_script(scripted_model), CourseStore(tmp_path), stream_tokens=True
    )

    # Act
    course = await builder.run("demo", course_id="course-fwd", run_id="run-fwd")

    # Assert — the builder asked the tap to stream tokens, and the build still completed.
    assert captured["stream_tokens"] is True
    assert course.status == CourseStatus.PUBLISHED


async def test_agent_interprets_the_request_into_a_brief_before_extraction(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    progress_sink,
    agent_sink,
    tmp_path: Path,
) -> None:
    # Arrange — the happy-path script now opens with interpret_request (the new front of the
    # pipeline). Capture both the coarse progress stages and the fine transcript to prove the brief
    # flows end-to-end, first, before any concept work.
    builder = _builder(_delegating_script(scripted_model), CourseStore(tmp_path))
    progress = progress_sink
    transcript = agent_sink

    # Act
    await builder.run(
        "Improve my English to CLB 10",
        course_id="course-brief",
        run_id="run-brief",
        progress=progress,
        agent=transcript,
    )

    # Assert — BRIEF_INTERPRETED is emitted right after the run starts and before concept
    # extraction, run_id-correlated. The interpret stage is the new front of the pipeline.
    stages = [event.stage for event in progress.events]
    assert ProgressStage.BRIEF_INTERPRETED in stages
    assert stages.index(ProgressStage.RUN_STARTED) < stages.index(ProgressStage.BRIEF_INTERPRETED)
    assert stages.index(ProgressStage.BRIEF_INTERPRETED) < stages.index(
        ProgressStage.CONCEPTS_EXTRACTED
    )
    brief_event = next(e for e in progress.events if e.stage is ProgressStage.BRIEF_INTERPRETED)
    assert brief_event.run_id == "run-brief"

    # The interpret_request tool surfaced the typed brief on the transcript as camelCase JSON
    # (subject / goal / targetLevel) — exactly what the live build canvas renders.
    results = [
        e
        for e in transcript.events
        if e.kind is AgentEventKind.TOOL_RESULT and e.tool == "interpret_request"
    ]
    assert results, "interpret_request produced no tool result on the transcript"
    payload = json.loads(results[0].result)
    assert payload["subject"] == _BRIEF.subject
    assert payload["goal"] == _BRIEF.goal
    assert payload["targetLevel"] == _BRIEF.target_level.value


async def test_agent_models_the_learner_between_the_brief_and_extraction(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    progress_sink,
    agent_sink,
    tmp_path: Path,
) -> None:
    # Arrange — a profiler that returns a non-empty frontier (the foundations an advanced learner
    # already has). The model-learner stage runs after interpret and before extraction.
    frontier = ["the English alphabet", "everyday vocabulary"]
    builder = _builder(
        _delegating_script(scripted_model),
        CourseStore(tmp_path),
        profiler=StubLearnerProfiler(LearnerProfile(frontier=frontier)),
    )

    # Act
    await builder.run(
        "Improve my English to CLB 10",
        course_id="course-frontier",
        run_id="run-frontier",
        progress=progress_sink,
        agent=agent_sink,
    )

    # Assert — LEARNER_MODELED is emitted after BRIEF_INTERPRETED and before CONCEPTS_EXTRACTED,
    # run_id-correlated (the frontier is modeled before the gap is extracted).
    stages = [event.stage for event in progress_sink.events]
    assert ProgressStage.LEARNER_MODELED in stages
    assert stages.index(ProgressStage.BRIEF_INTERPRETED) < stages.index(
        ProgressStage.LEARNER_MODELED
    )
    assert stages.index(ProgressStage.LEARNER_MODELED) < stages.index(
        ProgressStage.CONCEPTS_EXTRACTED
    )
    modeled = next(e for e in progress_sink.events if e.stage is ProgressStage.LEARNER_MODELED)
    assert modeled.run_id == "run-frontier"

    # The inferred frontier surfaced on the transcript (what extraction will skip teaching).
    results = [
        e
        for e in agent_sink.events
        if e.kind is AgentEventKind.TOOL_RESULT and e.tool == "model_learner"
    ]
    assert results, "model_learner produced no tool result on the transcript"
    payload = json.loads(results[0].result)
    assert payload["frontier"] == frontier
    assert payload["count"] == 2


async def test_agent_researches_the_standard_between_the_brief_and_the_learner(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    progress_sink,
    agent_sink,
    tmp_path: Path,
) -> None:
    # Arrange — a researcher returning grounded competency descriptors with provenance. The research
    # stage runs after the brief and before the learner is modeled (plan §4: interpret → research →
    # model the learner), so the learner model + extraction design against the real standard.
    builder = _builder(
        _delegating_script(scripted_model),
        CourseStore(tmp_path),
        researcher=StubStandardResearcher(_RESEARCH),
    )

    # Act
    await builder.run(
        "Improve my English to CLB 10",
        course_id="course-research",
        run_id="run-research",
        progress=progress_sink,
        agent=agent_sink,
    )

    # Assert — STANDARD_RESEARCHED lands after BRIEF_INTERPRETED and before LEARNER_MODELED,
    # run_id-correlated (the standard is grounded before the learner is modeled and the gap scoped).
    stages = [event.stage for event in progress_sink.events]
    assert ProgressStage.STANDARD_RESEARCHED in stages
    assert stages.index(ProgressStage.BRIEF_INTERPRETED) < stages.index(
        ProgressStage.STANDARD_RESEARCHED
    )
    assert stages.index(ProgressStage.STANDARD_RESEARCHED) < stages.index(
        ProgressStage.LEARNER_MODELED
    )
    researched = next(
        e for e in progress_sink.events if e.stage is ProgressStage.STANDARD_RESEARCHED
    )
    assert researched.run_id == "run-research"

    # The research_standard tool surfaced the grounded findings on the transcript as camelCase JSON
    # — the real competency descriptors plus structural provenance (URL + trust tier) the live build
    # canvas vets, not the model's memory.
    results = [
        e
        for e in agent_sink.events
        if e.kind is AgentEventKind.TOOL_RESULT and e.tool == "research_standard"
    ]
    assert results, "research_standard produced no tool result on the transcript"
    payload = json.loads(results[0].result)
    assert payload["status"] == "complete"
    assert "hear implied intent in speech" in payload["competencies"]
    assert payload["sources"][0]["url"] == "https://www.canada.ca/clb-10"
    assert payload["sources"][0]["trustTier"] == "official"


async def test_agent_discovers_grounding_between_curriculum_and_authoring(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    progress_sink,
    tmp_path: Path,
) -> None:
    # Arrange — the standard script now calls discover_grounding after design_curriculum and before
    # delegating authoring (the P6 seam where the discovery sub-graph will run).
    builder = _builder(_delegating_script(scripted_model), CourseStore(tmp_path))

    # Act
    await builder.run(
        "demo", course_id="course-ground", run_id="run-ground", progress=progress_sink
    )

    # Assert — GROUNDING_DISCOVERED lands after the curriculum is designed and before the first
    # lesson is authored, run_id-correlated (the corpus is prepared before claims are verified).
    stages = [event.stage for event in progress_sink.events]
    assert ProgressStage.GROUNDING_DISCOVERED in stages
    assert stages.index(ProgressStage.CURRICULUM_DESIGNED) < stages.index(
        ProgressStage.GROUNDING_DISCOVERED
    )
    assert stages.index(ProgressStage.GROUNDING_DISCOVERED) < stages.index(
        ProgressStage.MODULE_AUTHORED
    )
    grounded = next(
        e for e in progress_sink.events if e.stage is ProgressStage.GROUNDING_DISCOVERED
    )
    assert grounded.run_id == "run-ground"


class _AcceptAllJudge:
    """A relevance judge that keeps every source — isolates this test to the ingest + event path."""

    async def is_relevant(
        self, *, kc_label: str, kc_definition: str, text: str
    ) -> RelevanceVerdict:
        return RelevanceVerdict(True, "accepted (test judge)")


async def test_discovery_ingests_an_auto_source_into_the_course_corpus(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    agent_sink,
    tmp_path: Path,
) -> None:
    # Arrange — the live discoverer over a shared in-memory corpus (P6.3-T0 walking skeleton): the
    # discover_grounding stage runs the real discoverer, which ingests a graded, provenanced source
    # into THIS course's corpus and streams a source-vetting event onto the agent channel.
    corpus = InMemoryCorpusStore()
    embedder = StubEmbedder()
    # Stub search + extraction feed one fetchable page; the scorer grades it (OPEN) and an
    # accept-all judge keeps it (the judge's own logic is covered in test_discovery_loop.py), so the
    # live sub-graph ingests a real AUTO source end-to-end.
    page_url = "https://example.org/grounding"
    discoverer = SubgraphGroundingDiscoverer(
        StubSearchProvider([SearchResult(url=page_url, title="Grounding", snippet="…")]),
        StubContentExtractor(
            {
                page_url: ExtractedContent(
                    url=page_url, text="Reference material.", title="Grounding"
                )
            }
        ),
        CredibilityScorer(InMemorySourceAuthorityStore()),
        _AcceptAllJudge(),
        CorpusIngestor(embedder, corpus),
        clock=lambda: "2026-06-04T00:00:00+00:00",
    )
    builder = _builder(
        _delegating_script(scripted_model), CourseStore(tmp_path), discoverer=discoverer
    )

    # Act
    await builder.run("demo", course_id="course-auto", run_id="run-auto", agent=agent_sink)

    # Assert — the corpus now holds an auto-acquired source for the course, with its provenance.
    sources = await corpus.list_sources_for_course("course-auto")
    assert sources, "discovery ingested no source into the course corpus"
    assert all(s.acquisition_mode is AcquisitionMode.AUTO for s in sources)
    assert all(s.course_id == "course-auto" for s in sources)
    # The retriever can reach it scoped to this course (it is not a null-course/legacy chunk).
    (query_embedding,) = await embedder.embed(["demo"])
    evidence = await corpus.match(query_embedding, course_id="course-auto")
    assert evidence, "the ingested auto source is not retrievable for its course"
    # The discovery sub-graph streamed a structured source-vetting event, run_id-correlated, so the
    # canvas can render the live table (P6.3-T5) — not collapsed into one opaque tool call.
    evaluated = [e for e in agent_sink.events if e.kind is AgentEventKind.SOURCE_EVALUATED]
    assert evaluated, "discovery emitted no SOURCE_EVALUATED event"
    assert all(e.run_id == "run-auto" for e in evaluated)
    assert all(e.source is not None for e in evaluated), "SOURCE_EVALUATED event missing payload"
    assert all(e.source.accepted for e in evaluated if e.source is not None)


async def test_seed_grounding_ingests_a_research_source_into_the_course_corpus(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    progress_sink,
    tmp_path: Path,
) -> None:
    # Arrange — the live seeder over a shared in-memory corpus (P6.4-T0 walking skeleton): the
    # research stage already fetched a page (carried as a SeedSource), and seed_grounding ingests it
    # as a SEED source into THIS course's corpus, graded by the same credibility scorer the
    # discovery gate uses. No re-fetch — the seed carries the text the research stage already read.
    corpus = InMemoryCorpusStore()
    embedder = StubEmbedder()
    researcher = StubStandardResearcher(
        seeds=[
            SeedSource(
                url="https://ircc.canada.ca/clb10",
                text="CLB 10 listening: infer implied meaning and stance in extended speech.",
                title="CLB 10",
                trust_tier=TrustTier.OFFICIAL,
                fetched_at="2026-06-04T00:00:00+00:00",
            )
        ]
    )
    seeder = GroundingSeeder(
        CorpusIngestor(embedder, corpus, scorer=CredibilityScorer(InMemorySourceAuthorityStore()))
    )
    builder = _builder(
        _delegating_script(scripted_model),
        CourseStore(tmp_path),
        researcher=researcher,
        seeder=seeder,
    )

    # Act
    await builder.run("demo", course_id="course-seed", run_id="run-seed", progress=progress_sink)

    # Assert — the corpus now holds a SEED source for the course, provenance intact and credibility
    # FILLED by the ingestor's scorer: a seed is graded through the same gate, not blindly trusted.
    sources = await corpus.list_sources_for_course("course-seed")
    assert sources, "seeding ingested no source into the course corpus"
    assert all(s.acquisition_mode is AcquisitionMode.SEED for s in sources)
    assert all(s.course_id == "course-seed" for s in sources)
    assert all(s.trust_tier is TrustTier.OFFICIAL for s in sources)  # research's tier, preserved
    assert all(s.credibility is not None for s in sources)  # the scorer filled it at ingest
    # The retriever can reach the seed scoped to this course (not a null-course/legacy chunk).
    (query_embedding,) = await embedder.embed(["demo"])
    evidence = await corpus.match(query_embedding, course_id="course-seed")
    assert evidence, "the seeded source is not retrievable for its course"
    # The GROUNDING_SEEDED stage lit the Grounding phase, after the curriculum and before discovery,
    # run_id-correlated, so the live canvas can render it (P6.4-T2).
    stages = [event.stage for event in progress_sink.events]
    assert ProgressStage.GROUNDING_SEEDED in stages
    assert stages.index(ProgressStage.CURRICULUM_DESIGNED) < stages.index(
        ProgressStage.GROUNDING_SEEDED
    )
    assert stages.index(ProgressStage.GROUNDING_SEEDED) < stages.index(
        ProgressStage.GROUNDING_DISCOVERED
    )
    seeded = next(e for e in progress_sink.events if e.stage is ProgressStage.GROUNDING_SEEDED)
    assert seeded.run_id == "run-seed"


async def test_coverage_is_verified_at_finalize_before_the_run_completes(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    progress_sink,
    tmp_path: Path,
) -> None:
    # Walking skeleton (CQ Phase 4.2): the coverage critic runs at finalize as the last gate before
    # the course publishes. COVERAGE_VERIFIED lands after resources are curated and before the run
    # completes, run_id-correlated. The default critic is the deterministic fail-safe (no key); a
    # clean course still emits the stage (proving the seam), and publishes.
    # Arrange
    builder = _builder(_delegating_script(scripted_model), CourseStore(tmp_path))

    # Act
    course = await builder.run(
        "demo", course_id="course-cov", run_id="run-cov", progress=progress_sink
    )

    # Assert — the coverage stage is emitted in order, run_id-correlated, carrying gap_count=0 (the
    # field flows end-to-end), and a clean build still publishes (no gap on the all-grounded path).
    stages = [event.stage for event in progress_sink.events]
    assert ProgressStage.COVERAGE_VERIFIED in stages
    assert stages.index(ProgressStage.RESOURCES_CURATED) < stages.index(
        ProgressStage.COVERAGE_VERIFIED
    )
    assert stages.index(ProgressStage.COVERAGE_VERIFIED) < stages.index(ProgressStage.RUN_COMPLETED)
    verified = next(e for e in progress_sink.events if e.stage is ProgressStage.COVERAGE_VERIFIED)
    assert verified.run_id == "run-cov"
    assert verified.gap_count == 0
    assert course.status == CourseStatus.PUBLISHED


async def test_an_unbuilt_competency_is_scoped_out_and_withheld_for_review(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    progress_sink,
    tmp_path: Path,
) -> None:
    # Coverage gate (CQ Phase 4.2, owner Q3): a competency the standard promised but no module
    # builds is folded into the honest scope (excludes + scope_note) AND withholds publication
    # (REVIEW), rather than shipping a course that silently drops part of the standard. The research
    # stage grounds the competency; the stub plan tags no module with it, so the critic flags it.
    # Arrange
    store = CourseStore(tmp_path)
    research = StandardResearch(
        status=ResearchStatus.COMPLETE,
        competencies=["adapt register live in speech"],
        sources=[ResearchSource(url="https://www.canada.ca/clb-10", trust_tier=TrustTier.OFFICIAL)],
    )
    builder = _builder(
        _delegating_script(scripted_model),
        store,
        researcher=StubStandardResearcher(research),
        coverage_critic=DeterministicCoverageCritic(),
    )

    # Act
    course = await builder.run(
        "demo", course_id="course-gap", run_id="run-gap", progress=progress_sink
    )

    # Assert — the unbuilt competency is named in the honest scope (note + an excludes line), the
    # course is withheld for review, the stage reported one gap (run_id-correlated), round-tripped.
    assert course.scope is not None
    assert "adapt register live in speech" in course.scope_note
    assert any("adapt register live in speech" in line for line in course.scope.excludes)
    assert course.status == CourseStatus.REVIEW
    verified = next(e for e in progress_sink.events if e.stage is ProgressStage.COVERAGE_VERIFIED)
    assert verified.run_id == "run-gap"
    assert verified.gap_count == 1
    reloaded = store.load("course-gap")
    assert reloaded.status == CourseStatus.REVIEW
    assert reloaded.scope == course.scope


async def test_finalize_before_graph_is_rejected_gracefully(tmp_path: Path) -> None:
    # Arrange — the finalize tool over a draft whose prerequisite graph was never built. A weak
    # planner (e.g. the keyless local model) can call finalize out of order; the tool must refuse to
    # assemble a malformed course, but RECOVERABLY — returning a corrective result the agent can act
    # on, not raising into the agent loop and killing the run.
    draft = CourseDraft(topic="demo", course_id="course-2", run_id="run-2")
    finalize = make_finalize_course_tool(
        MinimalCritic(), CourseStore(tmp_path), draft, StubCoverageCritic()
    )

    # Act — finalize before the graph exists.
    result = await finalize.ainvoke({})

    # Assert — a corrective "incomplete" result naming the missing step; nothing assembled or saved.
    assert result["status"] == "incomplete"
    assert "build_prerequisite_graph" in result["error"]
    assert draft.course is None
    assert not (tmp_path / "course-2.json").exists()
