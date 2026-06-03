from typing import Protocol

from .extracted_content import ExtractedContent


class IContentExtractor(Protocol):
    """Fetches a URL and extracts its clean main text (P7.2 / P6 shared discovery layer).

    Centralizes both the fetch and the boilerplate stripping behind one Protocol (Trafilatura live,
    a stub offline), so the search provider only returns URLs and the network touches one place a
    per-build budget can cap. Best-effort and never raises: ``None`` collapses every non-result —
    an unreachable URL, a parse error, or a reachable page with no extractable text — into one
    "skip this source" signal the research stage handles uniformly.
    """

    async def extract(self, url: str) -> ExtractedContent | None: ...
