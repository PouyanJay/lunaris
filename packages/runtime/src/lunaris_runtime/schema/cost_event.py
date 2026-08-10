from pydantic import Field

from .base import CourseModel
from .enums import CostPocket, CostProvider, CostSubjectType


class CostEvent(CourseModel):
    """One row of the append-only cost ledger — a single paid (or metered) call during a build.

    Where ``SubjectCost`` is the one-row-per-subject rollup, this is the drill-through transcript:
    every Claude completion, embedding batch, web search, cover image, voiceover, and render, each
    with the *measured* usage and the *calculated* cost (``amount = usage x the price-book rate``).
    Costs are financial facts, so a row is immutable once written and stamps the
    ``price_book_version`` it was priced under — a later rate change never rewrites it.

    ``(subject_type, subject_id)`` is the rollup + purge key: one subject's cost aggregates every
    event across every run that spent on it — a course's main build *and* its separate video-job /
    cover-job runs, or a Live graph's compile and each later extension — so this is keyed by what
    was paid for, not by the run that paid. ``run_id`` is provenance (which run/job produced
    it); ``seq`` is the run-scoped emission
    index (mirrors ``RunEvent`` — ordering survives without a wall clock). ``usage`` is the raw
    measured units keyed by ``CostUnit`` value (e.g. ``{"input_tokens": …, "cache_read_tokens": …,
    "output_tokens": …}`` for Claude, or ``{"chars": …}`` / ``{"images": …}`` / ``{"search": …}`` /
    ``{"compute_seconds": …}``) — stored as-is so the calculation is auditable against the rate,
    which is priced per the same ``CostUnit``. ``pocket`` separates tenant BYOK
    spend from platform spend. The DB owns ``id`` and ``created_at`` for ops; neither is part of
    this contract (``seq`` is the order).
    """

    run_id: str
    subject_type: CostSubjectType
    # Bounded to match the column's own check: an over-long id is a failed insert, and cost
    # writes are best-effort, so it would be lost silently rather than refused loudly.
    subject_id: str = Field(min_length=1, max_length=100)
    seq: int
    component: str  # the pipeline stage that spent (e.g. "planner", "module_author", "render")
    provider: CostProvider
    model: str | None  # the model/voice/image id where one applies; None for search/render
    pocket: CostPocket
    usage: dict[str, object]  # the raw measured units this cost was calculated from
    amount: float  # calculated cost in `currency` (usage x the price-book rate)
    currency: str
    price_book_version: str
