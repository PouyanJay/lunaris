from dataclasses import dataclass, field


@dataclass(frozen=True)
class SegmentDraft:
    """One Merrill phase's content: prose plus the factual sentences to be verified."""

    prose: str
    claims: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LessonDraft:
    """A module author's output for one lesson — the four Merrill phases plus the arc's bookends.

    ``expects`` (entry expectations the lesson assumes) and ``self_check`` (self-assessment prompts)
    are the P7.3 arc compartments — personalized scaffolding, not verified claims. They default to
    empty so the legacy / novice author path stays valid without them.
    """

    activate: SegmentDraft
    demonstrate: SegmentDraft
    apply: SegmentDraft
    integrate: SegmentDraft
    expects: list[str] = field(default_factory=list)
    self_check: list[str] = field(default_factory=list)
