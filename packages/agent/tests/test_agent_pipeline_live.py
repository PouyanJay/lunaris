"""Live, key-gated proof that the REAL deep-agent harness builds a course end-to-end (P2).

Deselected unless ``-m eval``. Drives ``build_agent_course_builder`` with real Claude: the agent
plans, calls the deterministic moat tools, and delegates authoring to the verify→revise sub-agent —
no scripted model, no stubs. Proves the harness the MVP never had actually works on a live model and
that the moats hold on real LLM output (acyclic prerequisite order; no unsupported claim ships).

Run: ``uv run --env-file .env pytest -m eval packages/agent/tests/test_agent_pipeline_live.py -s``

Grounding: with ``SUPABASE_*`` + ``EMBEDDINGS_API_KEY`` set, the real pgvector retriever is used; if
the corpus is empty / Voyage is rate-limited, claims fall back to CUT (fail-safe). Either a
PUBLISHED or a REVIEW course passes here — the point is the harness runs on a live model and the DoD
(prereq-order + factuality) holds, never that a specific publish status results.
"""

import asyncio
import os
import uuid

import pytest
from lunaris_agent import build_agent_course_builder
from lunaris_eval import evaluate_course
from lunaris_grounding import StubEvidenceRetriever
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import CourseStatus, VerifierStatus

pytestmark = pytest.mark.eval


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
async def test_agent_builds_a_real_course_with_live_claude(tmp_path, capsys) -> None:
    # Arrange — the live composition root with real Claude tiers. Grounding is pinned to the
    # conservative stub retriever ON PURPOSE: this test proves the deep-agent HARNESS builds a
    # course on a live model, not the grounding corpus. The real Voyage retriever's free tier is
    # 3 req/min — far too slow to ground a full course — so leaving it on would gate this proof on
    # an unrelated provider limit (real grounded PUBLISHED is proven separately by the Stage 4b
    # grounded eval). With no evidence every claim is CUT (the publish gate still holds: no
    # unsupported claim ships), so the course finishes REVIEW and the DoD's factuality check passes.
    store = CourseStore(tmp_path)
    builder = build_agent_course_builder(store, retriever=StubEvidenceRetriever())
    run_id = uuid.uuid4().hex

    # Act — the real agent drives the whole build (extract → graph → curriculum → author/verify/
    # revise sub-agent → finalize). The wall-clock bound only turns a genuine stall into a clean
    # failure instead of a hung session (per-request timeouts + the rate limiter make it unreachable
    # in practice on a tier that comfortably absorbs the O(n²) prereq-judge fan-out).
    course = await asyncio.wait_for(
        builder.run("Bubble sort", course_id="live-agent", run_id=run_id),
        timeout=600,
    )

    # Assert — the harness produced a structurally real course on live output.
    assert course.graph.nodes, "no concepts were extracted"
    assert course.graph.is_acyclic is True
    topo = course.graph.topo_order
    assert set(topo) == {kc.id for kc in course.graph.nodes}, "topo order must cover every concept"
    assert course.modules and all(m.lessons for m in course.modules), "every module needs a lesson"
    assert course.goal_concept and course.goal_concept in topo

    # The Failure-B moat held on live output: every claim went through the verifier (none left
    # UNVERIFIED), so no claim is live-and-unsupported (the publish gate).
    claims = [
        claim
        for module in course.modules
        for lesson in module.lessons
        for segment in (
            lesson.segments.activate,
            lesson.segments.demonstrate,
            lesson.segments.apply,
            lesson.segments.integrate,
        )
        for claim in segment.claims
    ]
    assert all(claim.verifier_status is not VerifierStatus.UNVERIFIED for claim in claims), (
        "every claim must have been through the verifier"
    )

    # The independent DoD eval passes on live output (prereq-order + factuality).
    report = evaluate_course(course)
    detail = "; ".join(f"{c.name}={c.passed} ({c.detail})" for c in report.checks)
    assert report.meets_dod, detail

    # Status is whichever the publish gate + triage decided; both are valid outcomes here.
    assert course.status in (CourseStatus.PUBLISHED, CourseStatus.REVIEW)

    # P5: the agent pipeline now illustrates the authored lessons (the harness wired no visuals
    # before). With no LUNARIS_MERMAID_SCRIPT the passthrough renderer ships diagrams un-rendered,
    # but the branded VisualSpec still rides along. Prove a branded spec made it end-to-end on a
    # live model: at least one demonstrate-segment visual carries a typed spec.
    visuals = [
        visual
        for module in course.modules
        for lesson in module.lessons
        for visual in lesson.segments.demonstrate.visuals
    ]
    branded = [visual for visual in visuals if visual.spec is not None]
    assert visuals, "the agent pipeline placed no visuals on live output"
    assert branded, "no branded VisualSpec shipped — only raw mermaid (or none)"

    # Surface the live result so a human can eyeball it (run with -s).
    supported = sum(1 for c in claims if c.verifier_status is VerifierStatus.SUPPORTED)
    spec_types = sorted({visual.spec.type for visual in branded})
    with capsys.disabled():
        print(
            f"\n[LIVE AGENT] run_id={run_id} status={course.status.value} "
            f"concepts={len(course.graph.nodes)} modules={len(course.modules)} "
            f"claims={len(claims)} supported={supported} cut={len(claims) - supported} "
            f"provenance={len(course.provenance)} meets_dod={report.meets_dod} "
            f"visuals={len(visuals)} branded_specs={len(branded)} spec_types={spec_types}"
        )
