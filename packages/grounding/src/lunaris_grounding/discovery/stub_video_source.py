from collections.abc import Sequence

from .video_result import VideoResult


class StubVideoSource:
    """A deterministic video source for the no-key path + tests.

    Returns a preconfigured list for every query (capped at ``max_results``), or an empty list when
    unconfigured — so the curator degrades honestly to "no video found" offline, exactly as a real
    source returning nothing would. Tests inject canned results to drive the judge offline.
    """

    def __init__(self, results: Sequence[VideoResult] | None = None) -> None:
        self._results = list(results or [])

    async def find(self, query: str, *, max_results: int = 5) -> list[VideoResult]:
        return self._results[:max_results]
