from .base import CourseModel
from .enums import CourseStatus, ProgressStage


class ProgressEvent(CourseModel):
    """One streamed update from a course-build run (build-spec: live progress).

    Emitted by the orchestrator at each pipeline stage and streamed to the client as
    Server-Sent Events. Ordering is carried by a monotonic ``sequence`` ordinal rather
    than a wall-clock timestamp, so the deterministic test suite stays stable (the
    structlog trail already carries timestamps for operational use). ``run_id`` ties
    every event back to the run for cross-layer correlation.

    Stage-specific counts are optional and populated only where meaningful (e.g.
    ``kc_count``/``edge_count`` on GRAPH_BUILT, ``module_id`` on each MODULE_AUTHORED,
    the claim tallies on CLAIMS_VERIFIED, ``status`` on RUN_COMPLETED).
    """

    stage: ProgressStage
    label: str
    run_id: str
    sequence: int = 0
    kc_count: int | None = None
    edge_count: int | None = None
    module_count: int | None = None
    module_id: str | None = None
    claims_total: int | None = None
    claims_supported: int | None = None
    claims_cut: int | None = None
    status: CourseStatus | None = None
