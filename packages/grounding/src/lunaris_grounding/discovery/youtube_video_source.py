import re
from typing import Protocol

import structlog
from lunaris_runtime.credentials import resolve_secret

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
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
_WATCH_URL = "https://www.youtube.com/watch?v="
_TIMEOUT_S = 10.0  # a YouTube call is a single light GET; don't hang a build on a slow response
_ENRICH_PART = "snippet,contentDetails,statistics,status"
_VIDEOS_LIST_MAX_IDS = 50  # YouTube Data API: one videos.list call accepts at most 50 ids (1 unit)
# Quality pre-filters applied at search time (CQ Phase 2 T3) — cheap to set, narrow the pool before
# the (more expensive) enrichment + content judge. relevanceLanguage biases ranking (not a hard
# filter), so an English course's results surface English first; videoEmbeddable/safeSearch drop the
# unplayable and the unsafe up front.
_PREFILTERS = {"relevanceLanguage": "en", "videoEmbeddable": "true", "safeSearch": "moderate"}
_ISO_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _basics_from_search(payload: object) -> list[dict[str, str]]:
    """Map a ``search.list`` response into id/title/channel basics, tolerant of a shape change."""
    if not isinstance(payload, dict):
        return []
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    basics: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        video_id = identifier.get("videoId") if isinstance(identifier, dict) else None
        if not video_id:
            continue  # a non-video hit (channel/playlist) has no videoId — skip it
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        basics.append(
            {
                "id": str(video_id),
                "title": str(snippet.get("title", "")),
                "channel": str(snippet.get("channelTitle", "")),
            }
        )
    return basics


def _iso8601_to_seconds(duration: str) -> int | None:
    """Parse an ISO-8601 duration (``PT12M1S``) into whole seconds; None if it doesn't match."""
    match = _ISO_DURATION_RE.fullmatch(duration)
    if match is None or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(part) if part else 0 for part in match.groups())
    total = hours * 3600 + minutes * 60 + seconds
    return total or None  # PT0S (a scheduled/pre-live stream) carries no real duration signal


def _format_duration(total_seconds: int | None) -> str:
    """Human runtime ``H:MM:SS`` / ``M:SS`` from seconds; empty when unknown."""
    if total_seconds is None:
        return ""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _enrichment_by_id(payload: object) -> dict[str, dict[str, object]]:
    """Map a ``videos.list`` response into per-id enrichment dicts, tolerant of a shape change."""
    if not isinstance(payload, dict):
        return {}
    items = payload.get("items", [])
    if not isinstance(items, list):
        return {}
    enrichment: dict[str, dict[str, object]] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            enrichment[item["id"]] = item
    return enrichment


def _merge(basic: dict[str, str], detail: dict[str, object] | None) -> VideoResult:
    """Build a ``VideoResult`` from search basics + (optional) ``videos.list`` enrichment."""
    url = f"{_WATCH_URL}{basic['id']}"
    if detail is None:
        return VideoResult(url=url, title=basic["title"], channel=basic["channel"])
    snippet = detail.get("snippet") if isinstance(detail.get("snippet"), dict) else {}
    content = detail.get("contentDetails") if isinstance(detail.get("contentDetails"), dict) else {}
    stats = detail.get("statistics") if isinstance(detail.get("statistics"), dict) else {}
    status = detail.get("status") if isinstance(detail.get("status"), dict) else {}
    seconds = _iso8601_to_seconds(str(content.get("duration", "")))
    return VideoResult(
        url=url,
        title=basic["title"],
        channel=basic["channel"],
        duration=_format_duration(seconds),
        description=str(snippet.get("description", "")),
        duration_seconds=seconds,
        has_captions=str(content.get("caption", "")).lower() == "true",
        view_count=_as_int(stats.get("viewCount")),
        like_count=_as_int(stats.get("likeCount")),
        channel_id=str(snippet.get("channelId", "")),
        published_at=str(snippet.get("publishedAt", "")),
        embeddable=status.get("embeddable", True) is not False,
    )


class YouTubeVideoSource:
    """YouTube Data API ``IVideoSource`` (key-gated, lazy client, best-effort).

    Constructing it touches no network and needs no key; the ``YOUTUBE_API_KEY`` requirement and the
    HTTP client materialise on the first ``find``. ``find`` runs a quality-pre-filtered
    ``search.list`` then a single batched ``videos.list`` enrichment (CQ Phase 2 T3) so each result
    carries its description (for the content judge) + duration/captions/stats (for the scorer).
    Best-effort throughout: a missing key, a transport error, or an unexpected shape returns ``[]``
    (or, if only the enrichment fails, the search basics) — never an exception that breaks a build.
    ``client`` is an injectable async HTTP client for tests.
    """

    def __init__(
        self, *, api_key_env: str = _API_KEY_ENV, client: _HttpClient | None = None
    ) -> None:
        self._api_key_env = api_key_env
        self._client = client

    async def find(self, query: str, *, max_results: int = 5) -> list[VideoResult]:
        api_key = resolve_secret(self._api_key_env)
        if not api_key:
            logger.warning("youtube_search_unkeyed", reason=f"{self._api_key_env} unset")
            return []
        try:
            payload = await self._get(_SEARCH_URL, self._search_params(query, max_results, api_key))
        except Exception:
            logger.warning("youtube_search_failed", query=query, exc_info=True)
            return []
        basics = _basics_from_search(payload)
        if not basics:
            return []
        enrichment = await self._enrich([b["id"] for b in basics], api_key)
        return [_merge(basic, enrichment.get(basic["id"])) for basic in basics]

    @staticmethod
    def _search_params(query: str, max_results: int, api_key: str) -> dict[str, str]:
        return {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": str(max_results),
            "key": api_key,
            **_PREFILTERS,
        }

    async def _enrich(self, video_ids: list[str], api_key: str) -> dict[str, dict[str, object]]:
        """Batch one ``videos.list`` (≤50 ids, 1 quota unit) for the rich signals; {} on failure."""
        params = {
            "part": _ENRICH_PART,
            "id": ",".join(video_ids[:_VIDEOS_LIST_MAX_IDS]),
            "key": api_key,
        }
        try:
            return _enrichment_by_id(await self._get(_VIDEOS_URL, params))
        except Exception:
            logger.warning("youtube_enrich_failed", exc_info=True)
            return {}

    async def _get(self, url: str, params: dict[str, str]) -> object:
        """GET an endpoint and return its parsed JSON (one response-handling tail)."""
        response = await self._fetch(url, params)
        response.raise_for_status()
        return response.json()

    async def _fetch(self, url: str, params: dict[str, str]) -> _HttpResponse:
        """Issue the request via the injected client (tests) or a per-call httpx client.

        Isolated so ``httpx`` is imported lazily (no module-load cost / no key needed to construct)
        and a fake client can be injected without it.
        """
        if self._client is not None:
            return await self._client.get(url, params=params)
        import httpx

        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            return await client.get(url, params=params)
