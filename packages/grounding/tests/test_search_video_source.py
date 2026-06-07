"""The no-key video fallback (CQ Phase 2 T3): video candidates come from the shared search, and the
search snippet is carried as the description so the content judge still has something to score."""

from lunaris_grounding import SearchResult, StubSearchProvider
from lunaris_grounding.discovery.search_video_source import SearchVideoSource


async def test_carries_the_search_snippet_as_the_video_description() -> None:
    # Arrange — the shared search returns a result with a snippet (no YouTube key on this path).
    search = StubSearchProvider(
        [SearchResult(url="https://v.example/x", title="A talk", snippet="unscripted native-pace")]
    )
    source = SearchVideoSource(search)

    # Act
    videos = await source.find("advanced listening input")

    # Assert — the snippet becomes the description the judge reads (title alone isn't enough).
    assert len(videos) == 1
    assert videos[0].url == "https://v.example/x"
    assert videos[0].title == "A talk"
    assert videos[0].description == "unscripted native-pace"
