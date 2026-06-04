from dataclasses import dataclass


@dataclass(frozen=True)
class VideoResult:
    """One video candidate from an ``IVideoSource`` (P7.4 resource curation).

    A transient domain object that flows inside Python (not over the wire), so a frozen dataclass,
    not a schema. ``url`` is the only required field; ``channel``/``duration`` are best-effort
    signals a rich source (YouTube Data API) exposes and the shared-search fallback leaves blank.
    """

    url: str
    title: str = ""
    channel: str = ""
    duration: str = ""  # human-readable runtime, e.g. "12:01"
