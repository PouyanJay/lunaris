"""Live end-to-end pipeline eval: real topic -> extraction -> graph -> curriculum ->
Merrill authoring -> verifier publish gate, against live Claude.

NOTE: grounding uses a stub retriever until the Supabase pgvector corpus (D2) is wired
(Stage 4b). With no corpus, claims are CUT by the publish gate — so this eval proves the
pathway, lesson structure, and the gate, NOT factual grounding. The grounded eval lands
with the real retriever.

Excluded from the default run (marked ``eval``). Run with a real key (one run per minute
to stay under the rate tier):

    uv run --env-file .env pytest -m eval -q
"""

import os
from pathlib import Path

import pytest
from lunaris_agent import build_orchestrator
from lunaris_agent.lesson_claims import iter_claims
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import CourseStatus, VerifierStatus

pytestmark = pytest.mark.eval

_HAS_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not _HAS_KEY, reason="ANTHROPIC_API_KEY not set")
async def test_live_pipeline_builds_authors_and_gates(tmp_path: Path) -> None:
    # Arrange
    store = CourseStore(tmp_path)
    orchestrator = build_orchestrator(store)

    # Act — the full pathway against live Claude
    course = await orchestrator.run("how merge sort works", course_id="live-1", run_id="run-live-1")

    # Assert — graph is a valid, goal-last DAG
    assert course.status is CourseStatus.REVIEW
    assert len(course.graph.nodes) >= 3
    assert course.graph.is_acyclic
    pos = {kc_id: i for i, kc_id in enumerate(course.graph.topo_order)}
    for edge in course.graph.edges:
        assert pos[edge.from_] < pos[edge.to]
    assert pos[course.goal_concept] == len(course.graph.topo_order) - 1

    # Assert — backward design: difficulty monotonic, every objective assessed, KCs covered
    kc_ids = {kc.id for kc in course.graph.nodes}
    prev_difficulty = -1.0
    for module in course.modules:
        assert module.difficulty_index >= prev_difficulty
        prev_difficulty = module.difficulty_index
        item_ids = {item.id for item in module.assessment.items}
        for objective in module.objectives:
            assert objective.kc in kc_ids
            assert objective.assessed_by and set(objective.assessed_by) <= item_ids
    covered = {o.kc for m in course.modules for o in m.objectives}
    assert covered == kc_ids

    # Assert — every module has a Merrill lesson with all four phases authored
    all_lessons = [lesson for m in course.modules for lesson in m.lessons]
    assert len(all_lessons) == len(course.modules)
    for lesson in all_lessons:
        for segment in (
            lesson.segments.activate,
            lesson.segments.demonstrate,
            lesson.segments.apply,
            lesson.segments.integrate,
        ):
            assert segment.prose.strip()

    # Assert — the publish gate held: every claim is supported-or-cut (no live unsupported).
    # Without a corpus (Stage 4b pending) claims are CUT, which is the correct conservative gate.
    claims = list(iter_claims(all_lessons))
    assert all(
        c.supported_by is not None or c.verifier_status is VerifierStatus.CUT for c in claims
    )

    # persisted round-trips
    assert store.load("live-1") == course
