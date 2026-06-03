"""P7.2-T3 — the Trafilatura-backed IContentExtractor, tested offline via injected fetch/extract.

Centralizes fetch + boilerplate-stripping behind one extractor; best-effort, so an unreachable URL,
an empty page, or a library error all collapse to None (the research stage just skips that source).
Trafilatura is only imported lazily when the callables aren't injected, so these tests never fetch.
"""

from lunaris_grounding import ExtractedContent, TrafilaturaContentExtractor


async def test_returns_clean_text_for_a_fetchable_page() -> None:
    # Arrange
    extractor = TrafilaturaContentExtractor(
        fetch_html=lambda url: "<html><body>raw</body></html>",
        extract_text=lambda html: "Clean main text.",
    )

    # Act
    content = await extractor.extract("https://uni.edu/a")

    # Assert
    assert content == ExtractedContent(url="https://uni.edu/a", text="Clean main text.")


async def test_returns_none_when_the_fetch_yields_nothing() -> None:
    # Arrange — an unreachable page (fetch returns None).
    extractor = TrafilaturaContentExtractor(
        fetch_html=lambda url: None, extract_text=lambda html: "unused"
    )
    assert await extractor.extract("https://unreachable") is None


async def test_returns_none_when_the_extraction_is_blank() -> None:
    # Arrange — a page that fetches but has no extractable main text.
    extractor = TrafilaturaContentExtractor(
        fetch_html=lambda url: "<html/>", extract_text=lambda html: "   "
    )
    assert await extractor.extract("https://empty.page") is None


async def test_returns_none_when_the_fetch_step_raises() -> None:
    # Arrange — the fetch raises (e.g. a transport error).
    def _boom(_: str) -> str:
        raise RuntimeError("network error")

    extractor = TrafilaturaContentExtractor(fetch_html=_boom, extract_text=lambda html: "x")
    assert await extractor.extract("https://boom") is None


async def test_returns_none_when_the_extract_step_raises() -> None:
    # Arrange — the fetch succeeds but the parse raises (a distinct path through the try body).
    def _boom(_: str) -> str:
        raise RuntimeError("parse error")

    extractor = TrafilaturaContentExtractor(fetch_html=lambda url: "<html/>", extract_text=_boom)
    assert await extractor.extract("https://boom") is None
