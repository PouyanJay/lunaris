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
    """Records each GET and replays a payload, or raises a configured transport error."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None) -> None:
        self._payload = payload or {}
        self._error = error
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url: str, *, params: dict) -> _FakeResponse:
        self.calls.append((url, params))
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._payload)


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
