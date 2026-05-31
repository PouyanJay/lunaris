from datetime import datetime

from .base import CourseModel
from .enums import RunStatus


class CourseRun(CourseModel):
    """One row in the run-history index — a single course build, listed in the sidebar.

    Where ``Course`` is the pedagogical artifact, this is the operational record of *building*
    it: keyed by ``id`` (the course_id ``GET /api/courses/{id}`` re-opens), with the run's
    correlation ``run_id``, the originating ``topic``, the operational ``status``, and the
    knowledge-component / module counts captured at finish. Serialized camelCase (the web
    contract, via ``CourseModel``); the ``created_at`` / ``updated_at`` timestamps are owned by
    this record, not the course.
    """

    id: str  # one run per course in the MVP; this is the course_id the UI re-opens
    run_id: str
    topic: str
    status: RunStatus
    kc_count: int = 0
    module_count: int = 0
    created_at: datetime
    updated_at: datetime
