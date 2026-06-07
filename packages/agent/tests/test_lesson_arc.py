"""P7.3 walking skeleton — the lesson arc + module competency flow end-to-end.

The relevance fix gives each lesson a real arc that mirrors the standard — *what this lesson expects
→ strategies → worked example → practice → self-check* — and records the target skill on the module.
This skeleton proves the new structural fields traverse the whole assembly→finalize→persist→wire
path with trivial content, BEFORE any personalized-authoring behavior is added (that is T1/T2):

  author draft (expects / self_check) → LessonAssembler → Lesson
  architect plan (competency)         → CurriculumAssembler → Module
  draft → finalize_course → Course → CourseStore → camelCase wire

It drives the REAL assemblers + finalize tool + store, so the fields are proven on a finalized,
persisted course, not a hand-built one.
"""

from pathlib import Path

import structlog
from lunaris_agent.coverage_critic import StubCoverageCritic
from lunaris_agent.critic import MinimalCritic
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_finalize_course_tool
from lunaris_agent.subagents.curriculum_architect import (
    AssessmentItemPlan,
    CurriculumAssembler,
    CurriculumPlan,
    ModulePlan,
    ObjectivePlan,
)
from lunaris_agent.subagents.module_author import LessonAssembler, LessonDraft, SegmentDraft
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    BloomLevel,
    Edge,
    KnowledgeComponent,
    Module,
    PrerequisiteGraph,
)

_COMPETENCY = "hear implied intent in speech"


def _graph() -> PrerequisiteGraph:
    nodes = [
        KnowledgeComponent(
            id="intent",
            label="Hearing implied intent",
            definition="Infer unstated meaning from tone and context.",
            difficulty=0.5,
            bloom_ceiling=BloomLevel.ANALYZE,
        ),
        KnowledgeComponent(
            id="stance",
            label="Reading authorial stance",
            definition="Identify a writer's position from subtext.",
            difficulty=0.6,
            bloom_ceiling=BloomLevel.ANALYZE,
        ),
    ]
    return PrerequisiteGraph(
        nodes=nodes,
        edges=[Edge.model_validate({"from": "intent", "to": "stance", "strength": 0.8})],
        topo_order=["intent", "stance"],
        is_acyclic=True,
    )


def _plan() -> CurriculumPlan:
    """One module covering both KCs, mapped to a researched target competency."""
    return CurriculumPlan(
        modules=[
            ModulePlan(
                title="Listening for intent",
                kcs=["intent", "stance"],
                competency=_COMPETENCY,
                objectives=[
                    ObjectivePlan(
                        kc="intent",
                        statement="Given audio, the learner can analyze implied intent.",
                        bloom_level=BloomLevel.ANALYZE,
                        items=[AssessmentItemPlan("Identify the speaker's unstated request.")],
                    ),
                    ObjectivePlan(
                        kc="stance",
                        statement="Given a text, the learner can analyze authorial stance.",
                        bloom_level=BloomLevel.ANALYZE,
                        items=[AssessmentItemPlan("State the author's position and its evidence.")],
                    ),
                ],
            )
        ]
    )


def _arc_lesson(module: Module) -> LessonDraft:
    """A lesson draft carrying the new arc compartments alongside the Merrill phases."""
    return LessonDraft(
        activate=SegmentDraft("Recall a conversation where the real point was unstated.", []),
        demonstrate=SegmentDraft("Worked example: a hedged refusal, decoded line by line.", []),
        apply=SegmentDraft("Practice: decode three short clips.", []),
        integrate=SegmentDraft("Use it in your next meeting.", []),
        expects=[f"You can already follow everyday {module.title}."],
        self_check=[f"Can you decode an implied refusal in {module.title} unaided?"],
    )


def _draft_with_authored_modules(tmp_path: Path) -> tuple[CourseDraft, CourseStore]:
    """A run draft whose graph + competency-tagged modules carry authored arc lessons."""
    graph = _graph()
    modules = CurriculumAssembler().assemble(_plan(), graph)
    lesson_assembler = LessonAssembler()
    for module in modules:
        module.lessons = [
            lesson_assembler.assemble(_arc_lesson(module), lesson_id=f"{module.id}-l0")
        ]
    draft = CourseDraft(
        topic="Improve my English to CLB 10", course_id="course-arc", run_id="run-arc"
    )
    draft.graph = graph
    draft.modules = modules
    return draft, CourseStore(tmp_path)


async def test_finalized_course_carries_the_lesson_arc_and_module_competency(
    tmp_path: Path,
) -> None:
    # Arrange — a draft whose assembled module (competency-tagged) holds an arc-carrying lesson.
    draft, store = _draft_with_authored_modules(tmp_path)
    finalize = make_finalize_course_tool(MinimalCritic(), store, draft, StubCoverageCritic())

    # Act — the real finalize tool assembles, gates, and persists the course. Capture the structured
    # logs so the run_id correlation at the deepest layer this skeleton exercises can be asserted.
    with structlog.testing.capture_logs() as logs:
        await finalize.ainvoke({})
    course = draft.course
    assert course is not None

    # Assert — the single module records the researched competency it covers, and its lesson carries
    # the two new arc compartments, personalized to the module (author draft → LessonAssembler →
    # Lesson threads them through). One module/lesson by construction, so assert it directly.
    assert len(course.modules) == 1
    module = course.modules[0]
    assert module.competency == _COMPETENCY
    assert len(module.lessons) == 1
    lesson = module.lessons[0]
    assert lesson.expects == [f"You can already follow everyday {module.title}."]
    assert lesson.self_check == [f"Can you decode an implied refusal in {module.title} unaided?"]

    # The arc + competency survive persistence (assembled, saved, and reloaded intact).
    reloaded = store.load("course-arc")
    reloaded_lesson = reloaded.modules[0].lessons[0]
    assert reloaded.modules[0].competency == _COMPETENCY
    assert reloaded_lesson.expects and reloaded_lesson.self_check

    # run_id threads the finalize log (correlation everywhere — CLAUDE.md §4).
    assert any(
        event.get("event") == "agent_course_finalized" and event.get("run_id") == "run-arc"
        for event in logs
    )

    # The wire contract the web consumes is camelCase: self_check → selfCheck, competency present.
    module_wire = course.model_dump(by_alias=True)["modules"][0]
    assert module_wire["competency"] == _COMPETENCY
    lesson_wire = module_wire["lessons"][0]
    assert lesson_wire["expects"] == [f"You can already follow everyday {module_wire['title']}."]
    assert "selfCheck" in lesson_wire
