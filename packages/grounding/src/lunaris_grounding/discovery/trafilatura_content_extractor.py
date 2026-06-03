import asyncio
from collections.abc import Callable

import structlog

from .extracted_content import ExtractedContent

logger = structlog.get_logger()


class TrafilaturaContentExtractor:
    """Trafilatura-backed ``IContentExtractor``: fetch a URL + extract its clean main text.

    Centralizes fetch + boilerplate-stripping behind one extractor; Trafilatura's functions are
    synchronous, so each runs in a worker thread. Best-effort: an unreachable URL, an empty page, or
    a library error all collapse to ``None`` (the research stage simply skips that source), never an
    exception that breaks a build. ``fetch_html``/``extract_text`` are injectable for tests; left
    unset they lazily bind to ``trafilatura.fetch_url`` / ``trafilatura.extract``.
    """

    def __init__(
        self,
        *,
        fetch_html: Callable[[str], str | None] | None = None,
        extract_text: Callable[[str], str | None] | None = None,
    ) -> None:
        self._fetch_html = fetch_html
        self._extract_text = extract_text

    async def extract(self, url: str) -> ExtractedContent | None:
        try:
            fetch_html, extract_text = self._ensure_fns()
            html = await asyncio.to_thread(fetch_html, url)
            if not html:
                return None
            text = await asyncio.to_thread(extract_text, html)
        except Exception:
            logger.warning("trafilatura_extract_failed", url=url, exc_info=True)
            return None
        if not text or not text.strip():
            return None
        return ExtractedContent(url=url, text=text)

    def _ensure_fns(
        self,
    ) -> tuple[Callable[[str], str | None], Callable[[str], str | None]]:
        if self._fetch_html is None or self._extract_text is None:
            import trafilatura

            self._fetch_html = self._fetch_html or trafilatura.fetch_url
            self._extract_text = self._extract_text or trafilatura.extract
        return self._fetch_html, self._extract_text
