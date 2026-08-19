from collections.abc import Sequence

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
    return " ".join(parts)


def _joined(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]
