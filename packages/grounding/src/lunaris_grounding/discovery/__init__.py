"""Discovery — the shared web-search + content-extraction layer (P7.2; P6 consumes it later).

One acquisition dependency for the whole product: a ``ISearchProvider`` finds candidate URLs and a
``IContentExtractor`` fetches + cleans their main text, both Protocol-shaped so the backend stays
swappable and the no-key path uses deterministic stubs. P7's research-to-design stage and P6's
research-to-ground-claims stage both build on these primitives.
"""

from .content_extractor import IContentExtractor
from .extracted_content import ExtractedContent
from .search_provider import ISearchProvider
from .search_result import SearchResult
from .stub_content_extractor import StubContentExtractor
from .stub_search_provider import StubSearchProvider

__all__ = [
    "ExtractedContent",
    "IContentExtractor",
    "ISearchProvider",
    "SearchResult",
    "StubContentExtractor",
    "StubSearchProvider",
]
