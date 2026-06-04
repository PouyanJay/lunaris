import os
from typing import Protocol

import structlog

from .video_result import VideoResult

logger = structlog.get_logger()


class _HttpResponse(Protocol):
    """The slice of an HTTP response this adapter uses (httpx.Response satisfies it)."""

    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class _HttpClient(Protocol):
    """The slice of an async HTTP client this adapter uses — typed so tests can inject a fake."""

    async def get(self, url: str, *, params: dict[str, str]) -> _HttpResponse: ...


_API_KEY_ENV = "YOUTUBE_API_KEY"
_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_WATCH_URL = "https://www.youtube.com/watch?v="
_TIMEOUT_S = 10.0  # a YouTube search is a single light GET; don't hang a build on a slow response


def _to_videos(payload: object) -> list[VideoResult]:
    """Map a YouTube ``search.list`` response into ``VideoResult``s, tolerant of a shape change."""
    if not isinstance(payload, dict):
        return []
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    videos: list[VideoResult] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        video_id = identifier.get("videoId") if isinstance(identifier, dict) else None
        raw_snippet = item.get("snippet")
        snippet = raw_snippet if isinstance(raw_snippet, dict) else {}
        if not video_id:
            continue  # a non-video hit (channel/playlist) has no videoId — skip it
        videos.append(
            VideoResult(
                url=f"{_WATCH_URL}{video_id}",
                title=str(snippet.get("title", "")),
                channel=str(snippet.get("channelTitle", "")),
            )
        )
    return videos


class YouTubeVideoSource:
    """YouTube Data API ``IVideoSource`` (key-gated, lazy client, best-effort).

    Constructing it touches no network and needs no key; the ``YOUTUBE_API_KEY`` requirement and the
    HTTP client materialise on the first ``find``. Returns guaranteed-video results with their
    channel (richer than the shared-search fallback). Best-effort: a missing key (when the
    composition's key-gate is bypassed), a transport error, or an unexpected shape is logged and
    returns ``[]``, never an exception that breaks a build. ``client`` is an injectable async HTTP
    client for tests.

    (Duration/views enrichment via a follow-up ``videos.list`` call is a future refinement; this
    first cut returns the title + channel ``search.list`` exposes directly.)
    """

    def __init__(
        self, *, api_key_env: str = _API_KEY_ENV, client: _HttpClient | None = None
    ) -> None:
        self._api_key_env = api_key_env
        self._client = client

    async def find(self, query: str, *, max_results: int = 5) -> list[VideoResult]:
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            logger.warning("youtube_search_unkeyed", reason=f"{self._api_key_env} unset")
            return []
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": str(max_results),
            "key": api_key,
        }
        try:
            payload = await self._get(params)
        except Exception:
            logger.warning("youtube_search_failed", query=query, exc_info=True)
            return []
        return _to_videos(payload)

    async def _get(self, params: dict[str, str]) -> object:
        """GET the search endpoint and return its parsed JSON (one response-handling tail)."""
        response = await self._fetch(params)
        response.raise_for_status()
        return response.json()

    async def _fetch(self, params: dict[str, str]) -> _HttpResponse:
        """Issue the request via the injected client (tests) or a per-call httpx client.

        Isolated so ``httpx`` is imported lazily (no module-load cost / no key needed to construct)
        and a fake client can be injected without it.
        """
        if self._client is not None:
            return await self._client.get(_SEARCH_URL, params=params)
        import httpx

        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            return await client.get(_SEARCH_URL, params=params)
