"""Phase-2 T7 — the live grounding adapters read their key from the run credential scope.

In a multi-tenant build the key must be the *current user's* (carried in the ``run_credentials``
scope), never the process-global platform key. Each adapter resolves its key lazily on first use, so
these tests assert: inside a scope the tenant's key reaches the SDK client even when the platform
env key is absent (or different). No network — the SDK constructors / HTTP client are faked.
"""

from lunaris_runtime.credentials import run_credentials


class _SpyVoyage:
    last_api_key: str | None = None

    def __init__(self, *, model: str, api_key: str) -> None:
        type(self).last_api_key = api_key

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]


class _SpyTavily:
    last_api_key: str | None = None

    def __init__(self, *, api_key: str) -> None:
        type(self).last_api_key = api_key

    def search(self, query: str, *, max_results: int = 5) -> object:
        return {"results": []}


class _FakeHttpResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {"items": []}


class _RecordingHttpClient:
    """Captures the params each YouTube request is issued with (the api_key rides in ``params``)."""

    def __init__(self) -> None:
        self.params: list[dict[str, str]] = []

    async def get(self, url: str, *, params: dict[str, str]) -> _FakeHttpResponse:
        self.params.append(params)
        return _FakeHttpResponse()


async def test_voyage_embedder_uses_the_scoped_tenant_key(monkeypatch) -> None:
    # Arrange — platform key in env, tenant key in the run scope; no injected client.
    import langchain_voyageai

    monkeypatch.setattr(_SpyVoyage, "last_api_key", None)  # isolate from any prior test
    monkeypatch.setattr(langchain_voyageai, "VoyageAIEmbeddings", _SpyVoyage)
    monkeypatch.setenv("EMBEDDINGS_API_KEY", "platform-voyage")
    from lunaris_grounding import VoyageEmbedder

    # Act — embed inside the tenant scope.
    with run_credentials({"EMBEDDINGS_API_KEY": "tenant-voyage"}):
        await VoyageEmbedder().embed(["a sentence"])

    # Assert — the tenant key reached the SDK; the platform env key never did.
    assert _SpyVoyage.last_api_key == "tenant-voyage"


async def test_tavily_provider_uses_the_scoped_tenant_key(monkeypatch) -> None:
    import tavily

    monkeypatch.setattr(_SpyTavily, "last_api_key", None)  # isolate from any prior test
    monkeypatch.setattr(tavily, "TavilyClient", _SpyTavily)
    monkeypatch.setenv("SEARCH_API_KEY", "platform-search")
    from lunaris_grounding import TavilySearchProvider

    with run_credentials({"SEARCH_API_KEY": "tenant-search"}):
        await TavilySearchProvider().search("q")

    assert _SpyTavily.last_api_key == "tenant-search"


async def test_youtube_source_uses_the_scoped_tenant_key(monkeypatch) -> None:
    # Arrange — no platform env key at all; only the tenant's, via the scope.
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    from lunaris_grounding import YouTubeVideoSource

    client = _RecordingHttpClient()
    source = YouTubeVideoSource(client=client)

    # Act — with the scoped key, find proceeds past the unkeyed guard and issues the request.
    with run_credentials({"YOUTUBE_API_KEY": "tenant-youtube"}):
        await source.find("q")

    # Assert — a request was issued carrying the tenant key (not skipped as unkeyed).
    assert client.params and client.params[0]["key"] == "tenant-youtube"


async def test_youtube_source_is_unkeyed_outside_a_scope_when_env_absent(monkeypatch) -> None:
    # Tenant-only: a scope that lacks the key must NOT fall back to the platform env key.
    monkeypatch.setenv("YOUTUBE_API_KEY", "platform-youtube")
    from lunaris_grounding import YouTubeVideoSource

    client = _RecordingHttpClient()
    source = YouTubeVideoSource(client=client)

    with run_credentials({"SEARCH_API_KEY": "tenant-search"}):  # no youtube key in scope
        result = await source.find("q")

    # No request issued — the platform env key did not leak into the tenant build.
    assert result == []
    assert client.params == []
