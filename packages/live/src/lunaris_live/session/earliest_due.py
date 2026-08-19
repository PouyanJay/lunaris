from collections.abc import Iterable
from datetime import datetime


def earliest_due(due_ats: Iterable[datetime | None]) -> datetime | None:
    """The first of the given review days, skipping concepts nothing scheduled — ``None`` when
    nothing is (P2c T6). One helper for the two readers of "when is the first review": the refusal
    that names the day and the plain recap that names it."""
    days = [due_at for due_at in due_ats if due_at is not None]
    return min(days) if days else None
