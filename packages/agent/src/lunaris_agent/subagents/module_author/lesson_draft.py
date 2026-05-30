from dataclasses import dataclass, field


@dataclass(frozen=True)
class SegmentDraft:
    """One Merrill phase's content: prose plus the factual sentences to be verified."""

    prose: str
    claims: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LessonDraft:
    """A module author's output for one lesson — the four Merrill phases."""

    activate: SegmentDraft
    demonstrate: SegmentDraft
    apply: SegmentDraft
    integrate: SegmentDraft
