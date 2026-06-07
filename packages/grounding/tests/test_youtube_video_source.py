"""P7.4-T2 — the key-gated YouTube video source, driven by an injected fake HTTP client.

The live YouTube path can't be exercised without a key, so these tests inject a fake async client to
prove the adapter: it parses ``search.list`` into video results, carries the key + a video-only
filter on the request, stays key-gated (no key → empty, client untouched), and is best-effort
(a transport error → empty, never an exception).
"""

import pytest
from lunaris_grounding import YouTubeVideoSource

_PAYLOAD = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {"title": "Implied intent, decoded", "channelTitle": "EnglishPro"},
        },
        # A non-video hit (a channel) has no videoId — it must be skipped.
        {"id": {"kind": "youtube#channel"}, "snippet": {"title": "Some channel"}},
    ]
}


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """Records each GET and replays a payload, or raises a configured transport error.

    Returns the same payload for any URL (search.list + videos.list share it) — fine for the
    search-only assertions; the enrichment tests use ``_RoutingClient`` to return distinct payloads.
    """

    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self._payload = payload or {}
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url: str, *, params: dict) -> _FakeResponse:
        self.calls.append((url, params))
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._payload)


class _RoutingClient:
    """Routes ``search``/``videos`` GETs to distinct payloads; ``videos_error`` fails enrichment."""

    def __init__(
        self,
        search_payload: dict,
        videos_payload: dict | None = None,
        *,
        videos_error: Exception | None = None,
    ) -> None:
        self._search_payload = search_payload
        self._videos_payload = videos_payload or {}
        self._videos_error = videos_error
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url: str, *, params: dict) -> _FakeResponse:
        self.calls.append((url, params))
        if "/videos" in url:
            if self._videos_error is not None:
                raise self._videos_error
            return _FakeResponse(self._videos_payload)
        return _FakeResponse(self._search_payload)


_ENRICHED = {
    "items": [
        {
            "id": "abc123",
            "snippet": {
                "description": "A worked example halving the search range each comparison.",
                "channelId": "UC_chan",
                "publishedAt": "2024-01-02T00:00:00Z",
            },
            "contentDetails": {"duration": "PT12M1S", "caption": "true"},
            "statistics": {"viewCount": "150000", "likeCount": "4200"},
            "status": {"embeddable": True},
        }
    ]
}


async def test_parses_search_results_and_sends_a_keyed_video_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — a key in the env + a fake client returning a search.list payload.
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    client = _FakeClient(_PAYLOAD)
    source = YouTubeVideoSource(client=client)

    # Act
    videos = await source.find("hear implied intent", max_results=3)

    # Assert — only the video item is mapped, to a watch URL with its title + channel.
    assert len(videos) == 1
    assert videos[0].url == "https://www.youtube.com/watch?v=abc123"
    assert videos[0].title == "Implied intent, decoded"
    assert videos[0].channel == "EnglishPro"

    # The request hit the search endpoint as a keyed, video-only, snippet search for the query.
    request_url, params = client.calls[0]
    assert request_url == "https://www.googleapis.com/youtube/v3/search"
    assert params["type"] == "video"
    assert params["part"] == "snippet"
    assert params["q"] == "hear implied intent"
    assert params["key"] == "test-key"
    assert params["maxResults"] == "3"


async def test_returns_empty_and_skips_the_client_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — no key set; the client must never be touched (key-gated).
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    client = _FakeClient(_PAYLOAD)
    source = YouTubeVideoSource(client=client)

    # Act
    videos = await source.find("anything")

    # Assert
    assert videos == []
    assert client.calls == []


async def test_is_best_effort_on_a_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — a keyed source whose client raises on GET.
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    source = YouTubeVideoSource(client=_FakeClient(error=RuntimeError("boom")))

    # Act
    videos = await source.find("anything")

    # Assert — the failure is swallowed; the curator simply finds no video.
    assert videos == []


async def test_search_sends_quality_prefilters(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    client = _RoutingClient(_PAYLOAD, _ENRICHED)
    source = YouTubeVideoSource(client=client)

    # Act
    await source.find("hear implied intent")

    # Assert — the search call narrows the pool up front (CQ Phase 2 T3).
    _url, search_params = client.calls[0]
    assert search_params["relevanceLanguage"] == "en"
    assert search_params["videoEmbeddable"] == "true"
    assert search_params["safeSearch"] == "moderate"


async def test_enriches_each_video_via_a_batched_videos_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — search returns one video; videos.list returns its rich detail.
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    client = _RoutingClient(_PAYLOAD, _ENRICHED)
    source = YouTubeVideoSource(client=client)

    # Act
    videos = await source.find("hear implied intent")

    # Assert — the result carries the enriched content + scorer signals.
    assert len(videos) == 1
    video = videos[0]
    assert video.description.startswith("A worked example")
    assert video.duration_seconds == 721  # PT12M1S
    assert video.duration == "12:01"
    assert video.has_captions is True
    assert video.view_count == 150000
    assert video.like_count == 4200
    assert video.channel_id == "UC_chan"
    assert video.embeddable is True

    # The enrichment was a single batched, keyed videos.list over the search's ids.
    videos_calls = [c for c in client.calls if "/videos" in c[0]]
    assert len(videos_calls) == 1
    _url, videos_params = videos_calls[0]
    assert videos_params["id"] == "abc123"
    assert "contentDetails" in videos_params["part"]
    assert videos_params["key"] == "test-key"


async def test_enrichment_failure_degrades_to_search_basics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — search succeeds, videos.list raises.
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    client = _RoutingClient(_PAYLOAD, videos_error=RuntimeError("quota"))
    source = YouTubeVideoSource(client=client)

    # Act
    videos = await source.find("hear implied intent")

    # Assert — the title + channel survive (the basics); enrichment is simply absent, never a raise.
    assert len(videos) == 1
    assert videos[0].title == "Implied intent, decoded"
    assert videos[0].channel == "EnglishPro"
    assert videos[0].duration_seconds is None
    assert videos[0].description == ""
