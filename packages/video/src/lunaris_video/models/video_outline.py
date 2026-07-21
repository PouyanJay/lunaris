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
    # The scene's notable on-screen objects, surfaced as the chapter's key terms — the per-chapter
    # signal the reader matches resources against and highlights in the transcript. Empty only if
    # every object was blank after cleaning (`objects` is otherwise non-empty by schema); a scene
    # that fails to deserialize degrades the whole outline upstream.
    key_terms: tuple[str, ...] = ()


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
