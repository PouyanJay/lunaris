"""Shared cost-scope setup for the three composition roots that meter a run.

The course build (``CourseService``) and the cover / video workers each enter a cost scope around
their provider calls and drain it at the boundary. The construction ("build a scope, or ``None``
when metering is off") and the enter-or-no-op step are identical across all three, so they live
here once rather than tripled — each caller keeps only its one-line adapter that pulls ``run_id`` /
``course_id`` / ``owner_id`` from its own job or request.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext

from lunaris_runtime.persistence import ICostEventStore, ICourseCostStore
from lunaris_runtime.pricing import PriceBook

from .cost_scope import CostScope, cost_scope


def make_cost_scope(
    event_store: ICostEventStore | None,
    cost_store: ICourseCostStore | None,
    *,
    run_id: str,
    course_id: str,
    owner_id: str | None,
) -> CostScope | None:
    """A fresh cost scope for a run, or ``None`` when metering is off (either store unwired).

    Priced against the current checked-in price book; deep ``record_cost`` calls buffer into it, and
    the boundary drains it via ``drain_cost_scope``."""
    if event_store is None or cost_store is None:
        return None
    return CostScope(
        run_id=run_id,
        course_id=course_id,
        owner_id=owner_id,
        price_book=PriceBook.current(),
    )


@contextmanager
def enter_cost_scope(cost: CostScope | None) -> Iterator[CostScope | None]:
    """Enter ``cost`` for the block if present, else a no-op — for the ``with`` around a run's
    provider calls, so deep ``record_cost`` calls buffer into it."""
    manager: AbstractContextManager[object] = (
        cost_scope(cost) if cost is not None else nullcontext()
    )
    with manager:
        yield cost
