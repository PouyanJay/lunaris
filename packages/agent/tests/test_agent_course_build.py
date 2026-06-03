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
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.authoring import StubLessonReviser
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.event_tap import stream_course_build as real_stream_course_build
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
from lunaris_agent.subagents.goal_interpreter import StubGoalInterpreter
from lunaris_agent.subagents.learner_profiler import LearnerProfile, StubLearnerProfiler
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft
from lunaris_agent.subagents.standard_researcher import StubStandardResearcher
from lunaris_agent.subagents.visual_agent import (
    StubDiagramRenderer,
    StubVisualGenerator,
    VisualEngine,
)
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    AgentEventKind,
    BloomLevel,
    Citation,
    CourseBrief,
    CourseStatus,
    KnowledgeComponent,
    Level,
    Module,
    ProgressStage,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
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
                    item_prompts=["q"],
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
    profiler: StubLearnerProfiler | None = None,
    researcher: StubStandardResearcher | None = None,
    reviser: StubLessonReviser | None = None,
    verifier: Verifier | None = None,
    visual_engine: VisualEngine | None = None,
    stream_tokens: bool = False,
) -> AgentCourseBuilder:
    """Construct the agent course builder over the no-key stub subagents + real moats."""
    return AgentCourseBuilder(
        model,
        store,
        interpreter=StubGoalInterpreter(_BRIEF),
        profiler=profiler or StubLearnerProfiler(LearnerProfile(frontier=[])),
        researcher=researcher or StubStandardResearcher(),
        extractor=StubConceptExtractor(Extraction(kcs=_KCS, goal_id=_GOAL_ID)),
        builder=PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)),
        architect=StubCurriculumArchitect(_PLAN),
        reviser=reviser or _reviser(),
        verifier=verifier or _verifier(),
        visual_engine=visual_engine,
        stream_tokens=stream_tokens,
    )


def _delegating_script(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
    *,
    first_narration: str = "",
) -> object:
    """The standard happy-path agent script: interpret → research → model learner → extract →
    graph → curriculum → delegate → finalize.

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
