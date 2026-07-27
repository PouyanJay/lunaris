from datetime import datetime

from .base import CourseModel


class CourseCost(CourseModel):
    """The one-row-per-course cost rollup — "this course cost ~$X to build", with a breakdown.

    Where ``CostEvent`` is the append-only ledger, this is the materialized total the course
    Overview reads without scanning every row: the ``total_amount`` plus a ``breakdown``
    (per-component and per-provider subtotals, and the ``user_key`` vs ``platform`` pocket split).
    The ledger is the source of truth — the rollup is recomputed by summing *all* of a course's
    events. Keyed by ``course_id`` (the id ``GET /api/courses/{id}`` opens), so it accumulates every
    run that spent on the course: the initial build plus each separate video/cover job and any
    later regenerate. It is the course's *total* spend, not a single build's — a cover or video
    regenerate is real additional cost and adds to it. (The main build never re-runs under an
    existing ``course_id``; a new course always mints a fresh id.)

    ``price_book_version`` records the price book the rollup was last computed under (so a stale
    total is detectable when rates change). ``updated_at`` is owned by this record — the last time a
    job finished and refreshed the total.
    """

    course_id: str
    total_amount: float
    currency: str
    breakdown: dict[str, object]  # per-component / per-provider / per-pocket subtotals
    price_book_version: str
    updated_at: datetime
