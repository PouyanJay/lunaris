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
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft, StubModuleAuthor
from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.logging import clear_correlation, configure_logging
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import BloomLevel, Citation, CourseStatus, KnowledgeComponent, Module


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
    levels = ["comparison", "arrays", "loops", "sorted_order", "binary_search"]
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
            for kc_id in levels
        ]
    )


def _author_draft(module: Module) -> LessonDraft:
    # one verifiable claim per module's demonstrate phase, keyed by module id
    return LessonDraft(
        activate=SegmentDraft("recall", []),
        demonstrate=SegmentDraft("teach", [f"claim for {module.id}"]),
        apply=SegmentDraft("practice", []),
        integrate=SegmentDraft("transfer", []),
    )


async def test_full_pipeline_authors_and_verifies_with_publish_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — extract -> graph -> curriculum -> author -> verify, all offline via stubs.
    # Retriever returns evidence for every claim, so all claims should be SUPPORTED.
    clear_correlation()
    configure_logging(json_output=True)
    store = CourseStore(tmp_path)
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
    retriever = StubEvidenceRetriever(
        lambda claim: [Evidence(citation=Citation(id=f"src::{claim}", snippet=claim), score=0.9)]
    )
    verifier = Verifier(retriever, StubSupportAssessor())
    orchestrator = Orchestrator(
        store,
        StubConceptExtractor(_binary_search_extraction()),
        builder,
        StubCurriculumArchitect(_curriculum_plan()),
        StubModuleAuthor(_author_draft),
        verifier,
    )

    # Act
    course = await orchestrator.run("binary search", course_id="c1", run_id="run-7")
    clear_correlation()

    # Assert — full pathway passed the critic and PUBLISHED; lessons authored; claims cited
    assert course.status is CourseStatus.PUBLISHED
    assert all(m.lessons for m in course.modules)
    supported = [
        c for m in course.modules for lsn in m.lessons for c in lsn.segments.demonstrate.claims
    ]
    assert supported and all(c.supported_by for c in supported)
    assert course.provenance  # citations registered
    assert store.load("c1") == course

    entries = _json_lines(capsys.readouterr().out)
    events = {e["event"] for e in entries}
    assert {"prerequisite_graph_built", "claims_verified", "course_run_completed"} <= events
    assert all(e["run_id"] == "run-7" for e in entries)
