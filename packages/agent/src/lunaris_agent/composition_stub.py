from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import (
    BloomLevel,
    Citation,
    FlowEdge,
    FlowNode,
    FlowSpec,
    KnowledgeComponent,
    Module,
)

from .orchestrator import Orchestrator
from .subagents.concept_extractor import Extraction, StubConceptExtractor
from .subagents.curriculum_architect import (
    AssessmentItemPlan,
    CurriculumPlan,
    ModulePlan,
    ObjectivePlan,
    StubCurriculumArchitect,
)
from .subagents.module_author import LessonDraft, SegmentDraft, StubModuleAuthor
from .subagents.visual_agent import (
    StubDiagramRenderer,
    StubVisualGenerator,
    VisualDraft,
    VisualEngine,
)


def _demo_visual(concept: str, _context: str) -> VisualDraft:
    """A deterministic flow spec for the offline demo course; exercises the branded renderer."""
    return VisualDraft(
        source=f'graph TD\n  A["{concept}"] --> B["Apply it"]',
        spec=FlowSpec(
            title=concept,
            nodes=[FlowNode(id="learn", label=concept), FlowNode(id="apply", label="Apply it")],
            edges=[FlowEdge(from_="learn", to="apply", label="practice")],
        ),
    )


# A deterministic binary-search course — the offline/demo pipeline (no API key, no network).
_KCS = [
    (
        "comparison",
        "Comparison",
        "Deciding whether one value is less than, equal to, or greater than another.",
        0.10,
    ),
    ("arrays", "Arrays", "Contiguous, index-addressable sequences of elements.", 0.20),
    ("loops", "Loops", "Repeating a block of work until a condition is met.", 0.30),
    (
        "sorted_order",
        "Sorted Order",
        "The invariant that elements are arranged by a comparison key.",
        0.45,
    ),
    (
        "binary_search",
        "Binary Search",
        "Halving a sorted range each step to locate a target in logarithmic time.",
        0.75,
    ),
]
_EDGES = [
    ("comparison", "sorted_order"),
    ("arrays", "binary_search"),
    ("loops", "binary_search"),
    ("sorted_order", "binary_search"),
]


def build_stub_orchestrator(store: CourseStore) -> Orchestrator:
    """Composition root for the deterministic, offline pipeline.

    Wires the Stub subagents into an Orchestrator that builds a fixed binary-search course
    with grounded (SUPPORTED) claims — no API key or network. Used by the API/web for an
    offline demo and by integration tests that traverse every layer without live models.
    """
    extraction = Extraction(
        kcs=[
            KnowledgeComponent(
                id=kc_id,
                label=label,
                definition=definition,
                difficulty=difficulty,
                bloom_ceiling=BloomLevel.APPLY,
            )
            for kc_id, label, definition, difficulty in _KCS
        ],
        goal_id="binary_search",
    )
    plan = CurriculumPlan(
        modules=[
            ModulePlan(
                title=label,
                kcs=[kc_id],
                objectives=[
                    ObjectivePlan(
                        kc_id,
                        f"Given a problem, the learner can apply {label.lower()}.",
                        BloomLevel.APPLY,
                        [AssessmentItemPlan("q")],
                    )
                ],
            )
            for kc_id, label, _definition, _difficulty in _KCS
        ]
    )

    def author(module: Module) -> LessonDraft:
        return LessonDraft(
            activate=SegmentDraft("Recall what you already know.", []),
            demonstrate=SegmentDraft(
                "Worked example.", [f"{module.title} reduces the problem size each step."]
            ),
            apply=SegmentDraft("Try it yourself.", []),
            integrate=SegmentDraft("Connect it to the bigger picture.", []),
        )

    retriever = StubEvidenceRetriever(
        lambda claim: [
            Evidence(
                citation=Citation(id=f"src::{claim[:24]}", title="Reference", snippet=claim),
                score=0.9,
            )
        ]
    )
    return Orchestrator(
        store,
        StubConceptExtractor(extraction),
        PrerequisiteGraphBuilder(StubPrereqJudge(_EDGES)),
        StubCurriculumArchitect(plan),
        StubModuleAuthor(author),
        Verifier(retriever, StubSupportAssessor()),
        visual_engine=VisualEngine(StubVisualGenerator(_demo_visual), StubDiagramRenderer()),
    )
