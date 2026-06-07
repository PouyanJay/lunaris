from lunaris_agent.subagents.curriculum_architect import (
    AssessmentItemPlan,
    CurriculumAssembler,
    CurriculumPlan,
    ModulePlan,
    ObjectivePlan,
)
from lunaris_runtime.schema import BloomLevel, Edge, KnowledgeComponent, PrerequisiteGraph


def _graph() -> PrerequisiteGraph:
    nodes = [
        KnowledgeComponent(
            id="arrays",
            label="Arrays",
            definition="d",
            difficulty=0.2,
            bloom_ceiling=BloomLevel.UNDERSTAND,
        ),
        KnowledgeComponent(
            id="bsearch",
            label="Binary search",
            definition="d",
            difficulty=0.8,
            bloom_ceiling=BloomLevel.APPLY,
        ),
    ]
    return PrerequisiteGraph(
        nodes=nodes,
        edges=[Edge(from_="arrays", to="bsearch", strength=0.9)],
        frontier=[],
        is_acyclic=True,
        topo_order=["arrays", "bsearch"],
    )


def _plan() -> CurriculumPlan:
    return CurriculumPlan(
        modules=[
            ModulePlan(
                title="Foundations",
                kcs=["arrays"],
                objectives=[
                    ObjectivePlan(
                        "arrays",
                        "Given a list, describe indexing",
                        BloomLevel.UNDERSTAND,
                        [AssessmentItemPlan("q1")],
                    )
                ],
            ),
            ModulePlan(
                title="Search",
                kcs=["bsearch"],
                objectives=[
                    ObjectivePlan(
                        "bsearch",
                        "Given a sorted array, apply binary search",
                        BloomLevel.APPLY,
                        [AssessmentItemPlan("q2"), AssessmentItemPlan("q3")],
                    )
                ],
            ),
        ]
    )


def test_assemble_links_objectives_to_items() -> None:
    # Act
    modules = CurriculumAssembler().assemble(_plan(), _graph())

    # Assert — every objective references concrete items that exist in the assessment
    for module in modules:
        item_ids = {item.id for item in module.assessment.items}
        for objective in module.objectives:
            assert objective.assessed_by
            assert set(objective.assessed_by) <= item_ids


def test_assemble_stamps_the_gradeable_pass_criterion_onto_items() -> None:
    # Backward design (CQ Phase 4.1): the architect's per-item pass criterion is stamped onto the
    # assembled assessment Item, so the lesson can be authored backward from a concrete check.
    plan = CurriculumPlan(
        modules=[
            ModulePlan(
                title="Search",
                kcs=["bsearch"],
                objectives=[
                    ObjectivePlan(
                        "bsearch",
                        "Given a sorted array, apply binary search",
                        BloomLevel.APPLY,
                        [
                            AssessmentItemPlan(
                                "Trace it on [1,3,5,7].", "Finds 5 in <=3 comparisons."
                            )
                        ],
                    )
                ],
            )
        ]
    )

    # Act
    modules = CurriculumAssembler().assemble(plan, _graph())

    # Assert — the criterion rides onto the typed Item, paired with its prompt.
    item = modules[0].assessment.items[0]
    assert item.prompt == "Trace it on [1,3,5,7]."
    assert item.pass_criterion == "Finds 5 in <=3 comparisons."


def test_assemble_sets_non_decreasing_difficulty_index() -> None:
    # Act
    modules = CurriculumAssembler().assemble(_plan(), _graph())

    # Assert
    assert modules[0].difficulty_index == 0.2
    assert modules[1].difficulty_index == 0.8


def test_assemble_reorders_decreasing_difficulty() -> None:
    # Arrange — the architect emitted modules hardest-first (0.8 -> 0.2).
    reversed_plan = CurriculumPlan(modules=list(reversed(_plan().modules)))

    # Act — the assembler reorders to non-decreasing difficulty instead of crashing the build.
    modules = CurriculumAssembler().assemble(reversed_plan, _graph())

    # Assert — easy module leads, difficulty is non-decreasing, ids are sequential in that order.
    assert [m.difficulty_index for m in modules] == [0.2, 0.8]
    assert modules[0].title == "Foundations"
    assert [m.id for m in modules] == ["m0", "m1"]
