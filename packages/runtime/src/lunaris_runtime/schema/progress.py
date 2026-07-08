from collections.abc import Sequence

from .base import CourseModel
from .enums import CourseStatus, ProgressStage
from .instruction import Module
from .knowledge import PrerequisiteGraph


class CurriculumModuleMap(CourseModel):
    """One module's KC mapping, streamed on CURRICULUM_DESIGNED (P8 control room).

    Pairs with the per-module MODULE_AUTHORED events so the client can light each mapped
    knowledge component on the live blueprint as its module lands.
    """

    id: str
    title: str
    kcs: list[str]

    @classmethod
    def from_modules(cls, modules: Sequence[Module]) -> list["CurriculumModuleMap"]:
        """One row per course module — the single conversion point both pipelines share."""
        return [cls(id=module.id, title=module.title, kcs=list(module.kcs)) for module in modules]


class ProgressEvent(CourseModel):
    """One streamed update from a course-build run (build-spec: live progress).

    Emitted by the orchestrator at each pipeline stage and streamed to the client as
    Server-Sent Events. Ordering is carried by a monotonic ``sequence`` ordinal rather
    than a wall-clock timestamp, so the deterministic test suite stays stable (the
    structlog trail already carries timestamps for operational use). ``run_id`` ties
    every event back to the run for cross-layer correlation.

    Stage-specific counts are optional and populated only where meaningful (e.g.
    ``kc_count``/``edge_count`` on GRAPH_BUILT, ``module_id`` on each MODULE_AUTHORED,
    the claim tallies on CLAIMS_VERIFIED, ``gap_count`` on COVERAGE_VERIFIED,
    ``status`` on RUN_COMPLETED).
    """

    stage: ProgressStage
    label: str
    run_id: str
    sequence: int = 0
    # Intentionally redundant with ``graph`` below: clients rendering pre-P8 run logs (no
    # structured payload) still need the counts for the pipeline fallback.
    kc_count: int | None = None
    edge_count: int | None = None
    module_count: int | None = None
    module_id: str | None = None
    claims_total: int | None = None
    claims_supported: int | None = None
    claims_cut: int | None = None
    # The number of promised competencies left unbuilt on COVERAGE_VERIFIED (CQ Phase 4.2); 0 == a
    # clean course. None on every other stage.
    gap_count: int | None = None
    # The lesson-video tally on LESSON_VIDEOS (explainer-video V4): how many were enqueued and how
    # many degraded (failed / could not converge). ``videos_degraded`` > 0 renders the phase amber.
    # None on every other stage.
    videos_total: int | None = None
    videos_degraded: int | None = None
    status: CourseStatus | None = None
    # P8 control room: GRAPH_BUILT carries the validated structure itself (with the goal), and
    # CURRICULUM_DESIGNED the module → KC mapping — the client renders the live blueprint from
    # these instead of re-deriving structure from truncated tool results. None on every other
    # stage; absent entirely in pre-P8 run logs (clients must treat them as optional).
    graph: PrerequisiteGraph | None = None
    goal_concept: str | None = None
    modules: list[CurriculumModuleMap] | None = None
