"""P7.4 walking skeleton — vetted resources flow per-phase through curation → finalize → wire.

The "go beyond" attaches vetted external resources to each lesson's teaching phases. This skeleton
proves the new structural pieces traverse the whole path with stub content, BEFORE any real
search/vetting is added (that is T1/T2):

  curator → curate_resources tool → Segment.resources → finalize_course → Course → store → wire

It drives the REAL tool + finalize tool + store, so the resources are proven on a finalized,
persisted course, and the RESOURCES_CURATED stage streams.
"""

from pathlib import Path

from lunaris_agent.coverage_critic import StubCoverageCritic
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.progress_reporter import ProgressReporter
from lunaris_agent.harness.tools import make_curate_resources_tool, make_finalize_course_tool
from lunaris_agent.subagents.resource_curator import CuratedResources, StubResourceCurator
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    BloomLevel,
    KnowledgeComponent,
    Lesson,
    MerrillSegments,
    Module,
    PrerequisiteGraph,
    ProgressStage,
    Resource,
    ResourceKind,
    Segment,
    TrustTier,
)

_VIDEO = Resource(
    kind=ResourceKind.VIDEO,
    title="Decoding hedged disagreement",
    url="https://www.youtube.com/watch?v=abc",
    source="youtube.com",
    why="A 12-min worked example of reading implied intent in real interview clips.",
    trust_tier=TrustTier.OPEN,
    credibility=0.8,
    fetched_at="2026-06-03T00:00:00Z",
    duration="12:01",
)
_PRACTICE = Resource(
    kind=ResourceKind.PRACTICE,
    title="Inference drills",
    url="https://example.edu/drills",
    source="example.edu",
    why="Targeted practice on inferring unstated meaning.",
    trust_tier=TrustTier.REPUTABLE,
    credibility=0.7,
    fetched_at="2026-06-03T00:00:00Z",
)


def _graph() -> PrerequisiteGraph:
    nodes = [
        KnowledgeComponent(
            id="intent",
            label="Hearing implied intent",
            definition="Infer unstated meaning from tone and context.",
            difficulty=0.5,
            bloom_ceiling=BloomLevel.ANALYZE,
        )
    ]
    return PrerequisiteGraph(nodes=nodes, edges=[], topo_order=["intent"], is_acyclic=True)


def _segment(prose: str) -> Segment:
    return Segment(prose=prose)


def _module_with_lesson() -> Module:
    lesson = Lesson(
        id="m0-l0",
        segments=MerrillSegments(
            activate=_segment("Recall a hedged refusal."),
            demonstrate=_segment("A worked example, decoded."),
            apply=_segment("Decode three clips."),
            integrate=_segment("Use it in your next meeting."),
        ),
    )
    return Module(
        id="m0",
        title="Listening for intent",
        kcs=["intent"],
        competency="hear implied intent in speech",
        lessons=[lesson],
        difficulty_index=0.5,
    )


def _stub_curation(_module: Module) -> CuratedResources:
    """A stub curation: a worked-example video on demonstrate, a practice drill on apply."""
    return CuratedResources(demonstrate=[_VIDEO], apply=[_PRACTICE])


async def test_curate_resources_attaches_per_phase_resources_and_they_finalize(
    progress_sink,
    tmp_path: Path,
) -> None:
    # Arrange — a draft whose authored module/lesson is ready for curation.
    draft = CourseDraft(
        topic="Improve my English to CLB 10", course_id="course-res", run_id="run-res"
    )
    draft.graph = _graph()
    draft.modules = [_module_with_lesson()]
    draft.progress = ProgressReporter("run-res", progress_sink)
    store = CourseStore(tmp_path)
    curate = make_curate_resources_tool(StubResourceCurator(_stub_curation), draft)
    finalize = make_finalize_course_tool(MinimalCritic(), store, draft, StubCoverageCritic())

    # Act — the real curate tool attaches resources per phase, then finalize assembles + persists.
    await curate.ainvoke({})
    await finalize.ainvoke({})
    course = draft.course
    assert course is not None

    # Assert — the curated resources landed on the right Merrill phases, and phases the judge did
    # not assign stay empty (resources are aids, not required on every phase).
    segments = course.modules[0].lessons[0].segments
    demonstrate_kinds = [r.kind for r in segments.demonstrate.resources]
    apply_kinds = [r.kind for r in segments.apply.resources]
    assert demonstrate_kinds == [ResourceKind.VIDEO]
    assert segments.demonstrate.resources[0].url == "https://www.youtube.com/watch?v=abc"
    assert apply_kinds == [ResourceKind.PRACTICE]
    assert segments.activate.resources == []
    assert segments.integrate.resources == []

    # The resources survive persistence with their provenance + "why" intact.
    reloaded = store.load("course-res")
    reloaded_video = reloaded.modules[0].lessons[0].segments.demonstrate.resources[0]
    assert reloaded_video.why.startswith("A 12-min worked example")
    assert reloaded_video.fetched_at == "2026-06-03T00:00:00Z"

    # The wire contract the web consumes is camelCase: trust_tier → trustTier under resources.
    wire = course.model_dump(by_alias=True)["modules"][0]["lessons"][0]["segments"]["demonstrate"]
    assert wire["resources"][0]["trustTier"] == "open"
    assert wire["resources"][0]["kind"] == "video"

    # The curation stage streamed to the build canvas.
    stages = [event.stage for event in progress_sink.events]
    assert ProgressStage.RESOURCES_CURATED in stages


async def test_an_empty_module_is_flagged_in_the_scope_note(progress_sink, tmp_path: Path) -> None:
    # Arrange — a draft whose curator finds nothing for the module (the silent-zero case, T5).
    draft = CourseDraft(topic="Improve my English", course_id="course-empty", run_id="run-empty")
    draft.graph = _graph()
    draft.modules = [_module_with_lesson()]
    draft.progress = ProgressReporter("run-empty", progress_sink)
    store = CourseStore(tmp_path)
    curate = make_curate_resources_tool(StubResourceCurator(), draft)  # default → no resources
    finalize = make_finalize_course_tool(MinimalCritic(), store, draft, StubCoverageCritic())

    # Act
    await curate.ainvoke({})
    await finalize.ainvoke({})

    # Assert — the empty module is recorded as a gap and folded into the course's scope_note (no
    # silent zero), and the lesson still ships its verified content (resources are aids).
    assert draft.resource_coverage_gaps == ["Listening for intent"]
    assert draft.course is not None
    assert "Listening for intent" in (draft.course.scope_note or "")
    assert "without curated external resources" in (draft.course.scope_note or "")
