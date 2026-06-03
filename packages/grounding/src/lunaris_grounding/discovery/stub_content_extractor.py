from collections.abc import Mapping

from .extracted_content import ExtractedContent


class StubContentExtractor:
    """A deterministic content extractor for the no-key path + tests.

    Returns preconfigured content keyed by URL, or ``None`` for an unknown URL — mirroring a real
    extractor that fails to fetch/parse a page. Unconfigured it returns ``None`` for everything, so
    the research stage degrades honestly offline. Tests inject canned pages to drive distillation.
    """

    def __init__(self, pages: Mapping[str, ExtractedContent] | None = None) -> None:
        self._pages = dict(pages or {})

    async def extract(self, url: str) -> ExtractedContent | None:
        return self._pages.get(url)
