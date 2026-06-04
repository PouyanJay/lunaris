"""The run-scoped course draft: where the agent's tools accumulate authoritative results.

The deep agent reasons and decides *what to call*; the typed, structured results live HERE —
in deterministic Python — not in the model's message history. Each capability tool is a closure
over this draft: it writes its typed output (the prerequisite graph, the authored lessons, the
verified citations) into the draft, and ``finalize_course`` reads the fully-populated draft to
assemble the typed ``Course``. This keeps authoritative data off the LLM's formatting path
(parity + provenance), exactly as ``finalize`` requires.
"""

from dataclasses import dataclass, field

from lunaris_runtime.schema import (
    Citation,
    Clarification,
    Course,
    CourseBrief,
    KnowledgeComponent,
    Module,
    PrerequisiteGraph,
    RiskTier,
)

from .agent_reporter import AgentReporter
from .progress_reporter import ProgressReporter


@dataclass
class CourseDraft:
    """Mutable, per-run accumulator for the agent-built course (one instance per run).

    Not a domain entity that flows over the wire (those are the frozen schema models) — this is
    transient working state shared between the tools and ``finalize_course`` within a single run.
    """

    topic: str
    course_id: str
    run_id: str
    risk_tier: RiskTier = RiskTier.LOW
    # The interpreted request (P7), recorded by the interpret_request stage and read by later
    # stages. None until interpreted, or on a path that skips it — downstream readers treat it as
    # optional.
    brief: CourseBrief | None = None
    # The learner's opt-in confirm answers (P7.5), seeded by the runner from the build request. The
    # interpret_request stage merges them onto the inferred brief before recording it; None (the
    # default / skipped-clarifier path) leaves the inference untouched — today's inferred build.
    clarification: Clarification | None = None
    frontier: list[str] = field(default_factory=list)
    goal_concept: str | None = None
    concepts: list[KnowledgeComponent] = field(default_factory=list)
    graph: PrerequisiteGraph | None = None
    modules: list[Module] = field(default_factory=list)
    provenance: list[Citation] = field(default_factory=list)
    # Set by the authoring loop's triage when a goal-critical claim could not be grounded after the
    # revise budget: finalize then withholds PUBLISHED (REVIEW) even though the publish gate passed.
    needs_review: bool = False
    course: Course | None = None
    # Stage-boundary progress emitter shared by every draft-bound tool + the authoring loop. Not a
    # constructor arg: it defaults to a no-op reporter (so tests/batch runs need no wiring) and the
    # runner swaps in a streaming sink-backed reporter when the API requests SSE.
    progress: ProgressReporter = field(init=False)
    # Fine-grained transcript emitter, same lifecycle as ``progress``: the authoring subagent (which
    # the top-level event tap can't see into) emits its per-module reasoning beats here, so lesson
    # authoring + verification surface live instead of one opaque ``task`` call. No-op by default;
    # the runner swaps in the run's shared AgentReporter (same sink + cursor as the tap).
    agent: AgentReporter = field(init=False)

    def __post_init__(self) -> None:
        self.progress = ProgressReporter(self.run_id)
        self.agent = AgentReporter(self.run_id)
