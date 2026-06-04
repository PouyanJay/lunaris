from typing import Protocol

from .video_result import VideoResult


class IVideoSource(Protocol):
    """Finds candidate videos for a query (P7.4 resource curation).

    The seam behind the video-resource path: a rich source (the YouTube Data API, when a key is set)
    returns duration/channel signals, while the no-key fallback wraps the shared search provider.
    Best-effort — a transport failure surfaces as an empty list, never an exception that aborts a
    build; the curator simply finds no video for that lesson.
    """

    async def find(self, query: str, *, max_results: int = 5) -> list[VideoResult]: ...
