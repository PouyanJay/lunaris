from datetime import datetime

from pydantic import Field

from .base import CourseModel
from .enums import CostSubjectType


class SubjectCost(CourseModel):
    """The one-row-per-subject cost rollup — "this cost ~$X to build", with a breakdown.

    Where ``CostEvent`` is the append-only ledger, this is the materialized total the course
    Overview reads without scanning every row: the ``total_amount`` plus a ``breakdown``
    (per-component and per-provider subtotals, and the ``user_key`` vs ``platform`` pocket split).
    The ledger is the source of truth — the rollup is recomputed by summing *all* of a course's
    events. Keyed by ``(subject_type, subject_id)`` — a course, or a Live concept graph — so it
    accumulates every run that spent on that subject: a course's initial build plus each separate
    video/cover job and any later regenerate; a graph's compile plus each runtime extension. It
    is the course's *total* spend, not a single build's — a cover or video
    regenerate is real additional cost and adds to it. (The main build never re-runs under an
    existing ``course_id``; a new course always mints a fresh id.)

    ``price_book_version`` records the price book the rollup was last computed under (so a stale
    total is detectable when rates change). ``updated_at`` is owned by this record — the last time a
    job finished and refreshed the total.
    """

    subject_type: CostSubjectType
    # Bounded to match the column's own check: an over-long id is a failed insert, and cost
    # writes are best-effort, so it would be lost silently rather than refused loudly.
    subject_id: str = Field(min_length=1, max_length=100)
    total_amount: float
    currency: str
    breakdown: dict[str, object]  # per-component / per-provider / per-pocket subtotals
    price_book_version: str
    updated_at: datetime
