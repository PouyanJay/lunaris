from collections.abc import Sequence
from datetime import datetime

from .earliest_due import earliest_due
from .review_day import review_day
from .schema import Covered, CoveredOutcome

#: The plain recap: what a session says over itself when there is no tutor to say it better (the
#: offline path, and a provider down at the last minute). Deterministic on purpose.
_NOTHING = (
    "We didn't get as far as a concept today; next time we start at the beginning of {topic}."
)
_OPENING = "Today we worked on {topic}."


def recap_sentence(topic: str, covered: Sequence[Covered]) -> str:
    """A recap in plain sentences from the record alone (P2c T5)."""
    if not covered:
        return _NOTHING.format(topic=topic)
    demonstrated = [c.concept for c in covered if c.outcome is CoveredOutcome.DEMONSTRATED]
    forming = [c.concept for c in covered if c.outcome is CoveredOutcome.FORMING]
    introduced = [c.concept for c in covered if c.outcome is CoveredOutcome.INTRODUCED]
    parts = [_OPENING.format(topic=topic)]
    if demonstrated:
        parts.append(f"You showed you have {_joined(demonstrated)}.")
    if forming:
        parts.append(f"{_joined(forming)} {'is' if len(forming) == 1 else 'are'} still forming.")
    if introduced:
        pronoun = "it" if len(introduced) == 1 else "them"
        parts.append(f"We opened {_joined(introduced)} and did not get to check {pronoun} yet.")
    if forming or introduced:
        parts.append(f"Next time we pick up {(forming + introduced)[0]} first.")
    if (first := _first_review(covered)) is not None:
        day, names = first
        parts.append(f"Your first review is on {review_day(day)}: {_joined(names)}.")
    return " ".join(parts)


def _first_review(covered: Sequence[Covered]) -> tuple[datetime, list[str]] | None:
    """The earliest review day and what is due on it, in the order covered came (the map's)."""
    day = earliest_due(c.due_at for c in covered)
    if day is None:
        return None
    return day, [
        c.concept for c in covered if c.due_at is not None and c.due_at.date() == day.date()
    ]


def _joined(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]
