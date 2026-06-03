"""Discovery — the shared web-search + content-extraction layer (P7.2; P6 consumes it later).

One acquisition dependency for the whole product: a ``ISearchProvider`` finds candidate URLs and a
``IContentExtractor`` fetches + cleans their main text, both Protocol-shaped so the backend stays
swappable and the no-key path uses deterministic stubs. P7's research-to-design stage and P6's
research-to-ground-claims stage both build on these primitives.
"""

from .content_extractor import IContentExtractor
from .domain_trust import classify_domain, host
from .extracted_content import ExtractedContent
from .research_budget import ResearchBudget
from .resource_budget import ResourceBudget
from .search_provider import ISearchProvider
from .search_result import SearchResult
from .search_video_source import SearchVideoSource
from .stub_content_extractor import StubContentExtractor
from .stub_search_provider import StubSearchProvider
from .stub_video_source import StubVideoSource
from .tavily_search_provider import TavilySearchProvider
from .trafilatura_content_extractor import TrafilaturaContentExtractor
from .video_result import VideoResult
from .video_source import IVideoSource
from .youtube_video_source import YouTubeVideoSource

__all__ = [
    "ExtractedContent",
    "IContentExtractor",
    "ISearchProvider",
    "IVideoSource",
    "ResearchBudget",
    "ResourceBudget",
    "SearchResult",
    "SearchVideoSource",
    "StubContentExtractor",
    "StubSearchProvider",
    "StubVideoSource",
    "TavilySearchProvider",
    "TrafilaturaContentExtractor",
    "VideoResult",
    "YouTubeVideoSource",
    "classify_domain",
    "host",
]
