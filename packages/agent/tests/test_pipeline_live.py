"""Live end-to-end pipeline eval (Stage 2): real topic -> Claude extraction -> graph.

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
async def test_live_pipeline_builds_valid_graph_for_a_real_topic(tmp_path: Path) -> None:
    # Arrange
    store = CourseStore(tmp_path)
    orchestrator = build_orchestrator(store)

    # Act — the full Stage-2 pathway against live Claude
    course = await orchestrator.run("how merge sort works", course_id="live-1", run_id="run-live-1")

    # Assert — extraction produced a multi-KC course and the moat yielded a valid DAG
    assert course.status is CourseStatus.SEQUENCING
    assert len(course.graph.nodes) >= 3
    assert course.graph.is_acyclic
    assert course.goal_concept in {kc.id for kc in course.graph.nodes}

    pos = {kc_id: i for i, kc_id in enumerate(course.graph.topo_order)}
    for edge in course.graph.edges:
        assert pos[edge.from_] < pos[edge.to]
    # the goal is the most advanced concept — never first when there are prerequisites
    assert pos[course.goal_concept] == len(course.graph.topo_order) - 1

    # persisted round-trips
    assert store.load("live-1") == course
