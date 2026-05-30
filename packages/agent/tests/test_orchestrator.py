import json
from pathlib import Path

import pytest
from lunaris_agent.orchestrator import Orchestrator
from lunaris_agent.subagents.concept_extractor import Extraction, StubConceptExtractor
from lunaris_agent.subagents.curriculum_architect import (
    CurriculumPlan,
    ModulePlan,
    ObjectivePlan,
    StubCurriculumArchitect,
)
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_runtime.logging import clear_correlation, configure_logging
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import BloomLevel, CourseStatus, KnowledgeComponent


def _json_lines(captured: str) -> list[dict]:
    return [json.loads(line) for line in captured.splitlines() if line.strip().startswith("{")]


def _kc(kc_id: str, difficulty: float) -> KnowledgeComponent:
    return KnowledgeComponent(
        id=kc_id,
        label=kc_id,
        definition=kc_id,
        difficulty=difficulty,
        bloom_ceiling=BloomLevel.APPLY,
    )


def _binary_search_extraction() -> Extraction:
    return Extraction(
        kcs=[
            _kc("comparison", 0.1),
            _kc("arrays", 0.2),
            _kc("loops", 0.3),
            _kc("sorted_order", 0.45),
            _kc("binary_search", 0.75),
        ],
        goal_id="binary_search",
    )


def _curriculum_plan() -> CurriculumPlan:
    levels = [
        ("comparison", 0.1),
        ("arrays", 0.2),
        ("loops", 0.3),
        ("sorted_order", 0.45),
        ("binary_search", 0.75),
    ]
    return CurriculumPlan(
        modules=[
            ModulePlan(
                title=kc_id,
                kcs=[kc_id],
                objectives=[
                    ObjectivePlan(
                        kc_id, f"Given X, the learner can apply {kc_id}", BloomLevel.APPLY, ["q"]
                    )
                ],
            )
            for kc_id, _ in levels
        ]
    )


async def test_pipeline_extracts_builds_and_designs_with_correlated_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — topic -> KCs -> graph -> curriculum, all offline via stubs
    clear_correlation()
    configure_logging(json_output=True)
    store = CourseStore(tmp_path)
    extractor = StubConceptExtractor(_binary_search_extraction())
    builder = PrerequisiteGraphBuilder(
        StubPrereqJudge(
            [
                ("arrays", "binary_search"),
                ("loops", "binary_search"),
                ("sorted_order", "binary_search"),
                ("comparison", "sorted_order"),
            ]
        )
    )
    architect = StubCurriculumArchitect(_curriculum_plan())
    orchestrator = Orchestrator(store, extractor, builder, architect)

    # Act
    course = await orchestrator.run("binary search", course_id="c1", run_id="run-7")
    clear_correlation()

    # Assert — full pathway: extraction + moat + backward design, persisted, correlated
    assert course.status is CourseStatus.SEQUENCING
    assert course.goal_concept == "binary_search"
    assert course.graph.is_acyclic
    assert len(course.modules) == 5
    # backward design: every objective is assessed by real items
    for module in course.modules:
        item_ids = {item.id for item in module.assessment.items}
        for objective in module.objectives:
            assert set(objective.assessed_by) <= item_ids and objective.assessed_by
    assert store.load("c1") == course

    entries = _json_lines(capsys.readouterr().out)
    events = {e["event"] for e in entries}
    assert {"course_run_started", "prerequisite_graph_built", "course_run_completed"} <= events
    assert all(e["run_id"] == "run-7" for e in entries)
