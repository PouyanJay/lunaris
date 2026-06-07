from dataclasses import dataclass


@dataclass(frozen=True)
class VideoResult:
    """One video candidate from an ``IVideoSource`` (P7.4 resource curation).

    A transient domain object that flows inside Python (not over the wire), so a frozen dataclass,
    not a schema. ``url`` is the only required field; everything else is a best-effort signal a rich
    source (the YouTube Data API ``videos.list`` enrichment, CQ Phase 2 T3) exposes and the
    shared-search fallback mostly leaves blank. ``description`` feeds the content judge (T2);
    ``duration_seconds`` / ``has_captions`` / ``embeddable`` / the counts feed the scorer (T4).
    """

    url: str
    title: str = ""
    channel: str = ""
    duration: str = ""  # human-readable runtime, e.g. "12:01"
    description: str = ""
    duration_seconds: int | None = None
    has_captions: bool = False
    view_count: int | None = None
    like_count: int | None = None
    channel_id: str = ""
    published_at: str = ""  # ISO-8601 instant
    embeddable: bool = True
