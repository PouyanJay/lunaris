"""P7.2-T4 — the curriculum architect maps modules to the researched competencies.

The actual mapping is the model's job (prompt-driven), so it's proven end-to-end by the live eval;
here we prove deterministically the two things that DON'T need a model: ``build_curriculum_prompt``
tells the architect to align modules to the researched competencies when the brief carries them
(and stays the plain backward-design prompt without research), and the ``design_curriculum`` tool
passes the draft's brief into the architect so the threading actually reaches it.
"""

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
    CourseBrief,
    Edge,
    KnowledgeComponent,
    Level,
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

    # Assert — the architect is told to map modules to those competencies, and they appear verbatim.
    assert "Map the modules to these researched competencies" in prompt
    assert "hear implied intent in speech" in prompt
    assert "adapt register live in speech" in prompt
    # The ordered KCs still drive the grouping (backward design over the validated order).
    assert "Hearing implied intent" in prompt


def test_build_curriculum_prompt_is_plain_backward_design_without_research() -> None:
    # No brief / no research → the original backward-design prompt, no competency mapping section.
    prompt = build_curriculum_prompt(_graph(), None)

    assert "Reading authorial stance" in prompt  # the KCs still drive it
    assert "competenc" not in prompt.lower()  # no researched-competency mapping section


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
