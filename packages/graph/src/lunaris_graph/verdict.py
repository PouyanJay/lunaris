from dataclasses import dataclass


@dataclass(frozen=True)
class PrereqVerdict:
    """A judge's verdict on one ordered pair: is the prerequisite real, and how strong."""

    is_prereq: bool
    strength: float = 0.0
