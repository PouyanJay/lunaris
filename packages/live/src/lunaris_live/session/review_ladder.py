from datetime import timedelta

#: The first review of a concept held at a close: a day out (P2c T6). Then each rung is further,
#: by ``GROWTH``. Both are placeholders until there is session data to fit them to (SM-2's own
#: starting numbers, roughly), deliberately one function, and deliberately a *ladder* rather than a
#: forgetting curve: beliefs still do not decay across sessions (AD6's trigger stays open), so a
#: due date is the only pull the director feels from one sitting to the next.
FIRST_REVIEW = timedelta(days=1)
GROWTH = 2.5
#: The top of the ladder: a concept that has held this many closes in a row stays here. Eight
#: months out at x2.5 from a day (244 days), which is as far as a tutoring product's ladder has
#: any business reaching — and a geometric ladder with no top would, on a runaway writer, carry a
#: rung past anything a date can hold (found in review). The column's CHECK is the same bound.
LAST_RUNG = 7


def review_interval(stage: int) -> timedelta:
    """How far out the review is for a concept that has held at ``stage`` closes in a row.

    ``stage`` runs from one to ``LAST_RUNG``: a concept that has held at no close is not on the
    ladder and has no interval to read, and nothing is above the top — a caller asking for either
    is a caller that skipped the close.
    """
    if not 1 <= stage <= LAST_RUNG:
        raise ValueError(f"review stage {stage} is not a rung on the ladder")
    return FIRST_REVIEW * (GROWTH ** (stage - 1))
