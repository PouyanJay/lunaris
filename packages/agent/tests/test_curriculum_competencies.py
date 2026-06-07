"""P7.2-T4 — the curriculum architect maps modules to the researched competencies.

The actual mapping is the model's job (prompt-driven), so it's proven end-to-end by the live eval;
here we prove deterministically the two things that DON'T need a model: ``build_curriculum_prompt``
tells the architect to align modules to the researched competencies when the brief carries them
(and stays the plain backward-design prompt without research), and the ``design_curriculum`` tool
passes the draft's brief into the architect so the threading actually reaches it.
"""

from lunaris_agent.coverage import framework_coverage
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.harness.tools import make_design_curriculum_tool
from lunaris_agent.subagents.curriculum_architect import (
    CurriculumPlan,
    ModulePlan,
    ObjectivePlan,
    build_curriculum_prompt,
)
from lunaris_runtime.schema import (
    BloomLevel,
    CompetencyArea,
    CourseBrief,
    Edge,
    KnowledgeComponent,
    Level,
    Module,
    PrerequisiteGraph,
    ResearchSource,
    ResearchStatus,
    StandardResearch,
)


def _graph() -> PrerequisiteGraph:
    nodes = [
        KnowledgeComponent(
            id="intent",
            label="Hearing implied intent",
            definition="d",
            difficulty=0.5,
            bloom_ceiling=BloomLevel.ANALYZE,
        ),
        KnowledgeComponent(
            id="stance",
            label="Reading authorial stance",
            definition="d",
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


def _researched_brief() -> CourseBrief:
    return CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        target_level=Level.ADVANCED,
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            competencies=["hear implied intent in speech", "adapt register live in speech"],
            sources=[ResearchSource(url="https://www.canada.ca/clb-10")],
        ),
    )


def test_build_curriculum_prompt_maps_modules_to_researched_competencies() -> None:
    # Arrange — a researched brief grounding the standard's competencies, over a two-KC graph.
    brief = _researched_brief()

    # Act
    prompt = build_curriculum_prompt(_graph(), brief)

    # Assert — the architect is told to map modules to the researched framework, and the
    # competencies appear verbatim (a flat-only brief renders as a flat outline).
    assert "Map the modules to this researched competency framework" in prompt
    assert "hear implied intent in speech" in prompt
    assert "adapt register live in speech" in prompt
    # The ordered KCs still drive the grouping (backward design over the validated order).
    assert "Hearing implied intent" in prompt


def test_build_curriculum_prompt_asks_for_a_per_module_competency_field_with_research() -> None:
    # P7.3: the mapping is recorded structurally — the architect tags each module with the ONE
    # competency it builds, so the JSON shape must carry a "competency" field and instruct it.
    prompt = build_curriculum_prompt(_graph(), _researched_brief())

    assert '"competency"' in prompt
    assert "tag each module" in prompt.lower()


def test_build_curriculum_prompt_is_plain_backward_design_without_research() -> None:
    # No brief / no research → the original backward-design prompt, no competency mapping section,
    # and no competency field in the JSON shape (nothing to tag against).
    prompt = build_curriculum_prompt(_graph(), None)

    assert "Reading authorial stance" in prompt  # the KCs still drive it
    assert "competenc" not in prompt.lower()  # no researched-competency mapping section or field


def test_build_curriculum_prompt_omits_mapping_for_partial_research_with_no_competencies() -> None:
    # PARTIAL research that distilled no competencies (e.g. budget exhausted) must degrade to the
    # plain backward-design prompt — an empty mapping section is worse than none.
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        target_level=Level.ADVANCED,
        research=StandardResearch(
            status=ResearchStatus.PARTIAL,
            competencies=[],
            sources=[ResearchSource(url="https://www.canada.ca/clb-10")],
        ),
    )

    prompt = build_curriculum_prompt(_graph(), brief)

    assert "competenc" not in prompt.lower()


def test_build_curriculum_prompt_presents_the_competency_areas() -> None:
    # Arrange — research with a STRUCTURED framework (areas + descriptors), CQ Phase 1.3.
    brief = CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        target_level=Level.ADVANCED,
        research=StandardResearch(
            status=ResearchStatus.COMPLETE,
            areas=[
                CompetencyArea(name="Listening", competencies=["hear implied intent in speech"]),
                CompetencyArea(name="Speaking", competencies=["adapt register live in speech"]),
            ],
            sources=[ResearchSource(url="https://www.canada.ca/clb-10")],
        ),
    )

    # Act
    prompt = build_curriculum_prompt(_graph(), brief)

    # Assert — both area names AND both descriptors reach the architect, so modules are designed
    # backward from the standard's real areas, not a flat undifferentiated list.
    assert "Listening" in prompt
    assert "Speaking" in prompt
    assert "hear implied intent in speech" in prompt
    assert "adapt register live in speech" in prompt


def test_framework_coverage_splits_covered_and_uncovered_competencies() -> None:
    # Arrange — three researched competencies; the curriculum tags two modules, one with a verbatim
    # competency and one with an invented tag (structure that drifted from the research).
    research = StandardResearch(
        status=ResearchStatus.PARTIAL, competencies=["alpha", "beta", "gamma"]
    )
    modules = [
        Module(id="m1", title="M1", competency="alpha"),
        Module(id="m2", title="M2", competency="invented"),
    ]

    # Act
    covered, uncovered = framework_coverage(research, modules)

    # Assert — only the verbatim-tagged competency is covered; the rest are flagged, in order.
    assert covered == ["alpha"]
    assert uncovered == ["beta", "gamma"]


async def test_design_curriculum_tool_passes_the_brief_to_the_architect() -> None:
    # Arrange — a draft carrying a researched brief + the prerequisite graph the architect needs.
    draft = CourseDraft(topic="English", course_id="c", run_id="r")
    draft.brief = _researched_brief()
    draft.graph = _graph()

    class _RecordingArchitect:
        def __init__(self) -> None:
            self.briefs: list[CourseBrief | None] = []

        async def design(
            self, graph: PrerequisiteGraph, *, brief: CourseBrief | None = None
        ) -> CurriculumPlan:
            self.briefs.append(brief)
            return CurriculumPlan(
                modules=[
                    ModulePlan(
                        title="M",
                        kcs=["intent", "stance"],
                        objectives=[
                            ObjectivePlan(
                                kc="intent",
                                statement="Given audio, the learner can infer intent.",
                                bloom_level=BloomLevel.ANALYZE,
                                item_prompts=["q"],
                            ),
                            ObjectivePlan(
                                kc="stance",
                                statement="Given text, the learner can identify stance.",
                                bloom_level=BloomLevel.ANALYZE,
                                item_prompts=["q"],
                            ),
                        ],
                    )
                ]
            )

    architect = _RecordingArchitect()
    tool = make_design_curriculum_tool(architect, draft)

    # Act
    await tool.ainvoke({})

    # Assert — the tool threaded the draft's brief into the architect (so competencies reach it).
    assert architect.briefs == [draft.brief]
