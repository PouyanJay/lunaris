from dataclasses import dataclass


@dataclass(frozen=True)
class OutlineChapter:
    """One scene surfaced as a navigable chapter of the Cinema player, with its span on the
    concatenated timeline. Distinct from ``schemas.chapter.Chapter`` (a titled RUN of scenes in a
    chaptered overview video) — this is a single scene's timeline window."""

    id: str
    title: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class TranscriptCue:
    """One spoken beat with its timed span on the concatenated timeline."""

    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True)
class VideoOutline:
    """The Cinema outline of a ready video: navigable chapters + a timed transcript."""

    chapters: list[OutlineChapter]
    transcript: list[TranscriptCue]
