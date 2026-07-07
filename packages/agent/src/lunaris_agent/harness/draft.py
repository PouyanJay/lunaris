"""The run-scoped course draft: where the agent's tools accumulate authoritative results.

The deep agent reasons and decides *what to call*; the typed, structured results live HERE —
in deterministic Python — not in the model's message history. Each capability tool is a closure
over this draft: it writes its typed output (the prerequisite graph, the authored lessons, the
verified citations) into the draft, and ``finalize_course`` reads the fully-populated draft to
assemble the typed ``Course``. This keeps authoritative data off the LLM's formatting path
(parity + provenance), exactly as ``finalize`` requires.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from lunaris_runtime.schema import (
    Citation,
    Clarification,
    Course,
    CourseBrief,
    DiscoveryDepth,
    KnowledgeComponent,
    Module,
    PrerequisiteGraph,
    RiskTier,
    VideoKind,
)
from lunaris_runtime.video_build import IVideoBuildCoordinator

from .agent_reporter import AgentReporter
from .progress_reporter import ProgressReporter

if TYPE_CHECKING:
    from ..subagents.standard_researcher import SeedSource


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
    # How hard auto-discovery (P6.3) searches, chosen up front by the learner. STANDARD = the
    # moderate default; THOROUGH widens the discovery budget. Read by the discovery stage only.
    discovery_depth: DiscoveryDepth = DiscoveryDepth.STANDARD
    # The composer's "Official sources only" switch (P5): when true, the grounding verifier applies
    # its curated-or-agreement trust floor at EVERY risk tier, not just HIGH. Read by the authoring
    # loop when it calls verify(). Default false = today's risk-tiered floor exactly.
    official_only: bool = False
    # The pages the research stage (P7.2) already fetched + extracted, carried forward so the
    # seed_grounding stage (P6.4) ingests them into the corpus without re-fetching. Populated by
    # research_standard; empty on the no-key / unavailable path. Harness-only; never on the wire.
    research_seeds: list["SeedSource"] = field(default_factory=list)
    frontier: list[str] = field(default_factory=list)
    goal_concept: str | None = None
    concepts: list[KnowledgeComponent] = field(default_factory=list)
    graph: PrerequisiteGraph | None = None
    modules: list[Module] = field(default_factory=list)
    provenance: list[Citation] = field(default_factory=list)
    # Set by the authoring loop's triage when a goal-critical claim could not be grounded after the
    # revise budget: finalize then withholds PUBLISHED (REVIEW) even though the publish gate passed.
    needs_review: bool = False
    # Module titles whose curation came up empty even after the broaden-retry (CQ Phase 2 T5).
    # finalize folds them into the course's scope_note so the learner sees the gap — no silent zero.
    resource_coverage_gaps: list[str] = field(default_factory=list)
    course: Course | None = None
    # Video V4: the build's video-enqueue coordinator, set by the runner from the run-scope
    # ``ContextVar`` (None when video generation is off → the authoring loop enqueues nothing). The
    # gate lives in the composition root; the harness only checks presence.
    video_coordinator: IVideoBuildCoordinator | None = None
    # lesson_id → job_id for every lesson video the build enqueued (the authoring loop fills this as
    # modules clear verification; finalize awaits these jobs in V4-T1). Per-build, harness-only.
    enqueued_video_jobs: dict[str, str] = field(default_factory=dict)
    # kind → job_id for the course-level videos (SUMMARY trailer, OVERVIEW intro) the build enqueued
    # once the curriculum is designed (V5-T2); finalize awaits these and stitches Course.videos.
    enqueued_course_videos: dict[VideoKind, str] = field(default_factory=dict)
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
