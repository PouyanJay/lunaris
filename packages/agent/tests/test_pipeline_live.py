"""Live end-to-end pipeline eval: real topic -> Claude extraction -> graph -> curriculum.

Excluded from the default run (marked ``eval``). Run with a real key:

    uv run --env-file .env pytest -m eval -q
"""

import os
from pathlib import Path

import pytest
from lunaris_agent import build_orchestrator
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import CourseStatus

pytestmark = pytest.mark.eval

_HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
async def test_live_pipeline_builds_valid_graph_and_curriculum(tmp_path: Path) -> None:
    # Arrange
    store = CourseStore(tmp_path)
    orchestrator = build_orchestrator(store)

    # Act — the full pathway (extract -> graph -> curriculum) against live Claude
    course = await orchestrator.run("how merge sort works", course_id="live-1", run_id="run-live-1")

    # Assert — graph is a valid, goal-last DAG
    assert course.status is CourseStatus.SEQUENCING
    assert len(course.graph.nodes) >= 3
    assert course.graph.is_acyclic
    pos = {kc_id: i for i, kc_id in enumerate(course.graph.topo_order)}
    for edge in course.graph.edges:
        assert pos[edge.from_] < pos[edge.to]
    assert pos[course.goal_concept] == len(course.graph.topo_order) - 1

    # Assert — backward design held: modules exist, every objective is assessed,
    # difficulty is non-decreasing, and each objective covers a real KC
    assert course.modules
    kc_ids = {kc.id for kc in course.graph.nodes}
    prev_difficulty = -1.0
    for module in course.modules:
        assert module.difficulty_index >= prev_difficulty
        prev_difficulty = module.difficulty_index
        item_ids = {item.id for item in module.assessment.items}
        for objective in module.objectives:
            assert objective.kc in kc_ids
            assert objective.assessed_by and set(objective.assessed_by) <= item_ids

    # Assert — every graph KC is covered by an objective (backward design)
    covered = [o.kc for m in course.modules for o in m.objectives]
    assert set(covered) == kc_ids

    # persisted round-trips
    assert store.load("live-1") == course
