from .base import CourseModel
from .enums import CostPocket, CostProvider


class CostEvent(CourseModel):
    """One row of the append-only cost ledger — a single paid (or metered) call during a build.

    Where ``CourseCost`` is the one-row-per-course rollup, this is the drill-through transcript:
    every Claude completion, embedding batch, web search, cover image, voiceover, and render, each
    with the *measured* usage and the *calculated* cost (``amount = usage x the price-book rate``).
    Costs are financial facts, so a row is immutable once written and stamps the
    ``price_book_version`` it was priced under — a later rate change never rewrites it.

    ``course_id`` is the rollup + purge key: one course's cost aggregates every event across the
    main build run *and* the separate video-job / cover-job runs, so this is keyed by course, not
    run. ``run_id`` is provenance (which run/job produced it); ``seq`` is the run-scoped emission
    index (mirrors ``RunEvent`` — ordering survives without a wall clock). ``usage`` is the raw
    measured units keyed by ``CostUnit`` value (e.g. ``{"input_tokens": …, "cache_read_tokens": …,
    "output_tokens": …}`` for Claude, or ``{"chars": …}`` / ``{"images": …}`` / ``{"search": …}`` /
    ``{"compute_seconds": …}``) — stored as-is so the calculation is auditable against the rate,
    which is priced per the same ``CostUnit``. ``pocket`` separates tenant BYOK
    spend from platform spend. The DB owns ``id`` and ``created_at`` for ops; neither is part of
    this contract (``seq`` is the order).
    """

    run_id: str
    course_id: str
    seq: int
    component: str  # the pipeline stage that spent (e.g. "planner", "module_author", "render")
    provider: CostProvider
    model: str | None  # the model/voice/image id where one applies; None for search/render
    pocket: CostPocket
    usage: dict[str, object]  # the raw measured units this cost was calculated from
    amount: float  # calculated cost in `currency` (usage x the price-book rate)
    currency: str
    price_book_version: str
