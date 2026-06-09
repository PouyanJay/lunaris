import asyncio

import structlog

from .search_result import SearchResult

logger = structlog.get_logger()


def _to_results(raw: object) -> list[SearchResult]:
    # A url-less hit is unfetchable by the extraction layer, so drop it here rather than surface it.
    if not isinstance(raw, list):
        return []
    results: list[SearchResult] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("href") or item.get("url") or "").strip()
        if url:
            results.append(
                SearchResult(
                    url=url,
                    title=str(item.get("title", "")),
                    snippet=str(item.get("body", "")),
                )
            )
    return results


class DuckDuckGoSearchProvider:
    """Keyless DuckDuckGo-backed ``ISearchProvider`` — the search fallback when no Tavily key.

    Needs no API key: the ``ddgs`` library queries DuckDuckGo directly. Its client is synchronous,
    so the call runs in a worker thread. Best-effort like Tavily: any failure (transport, rate
    limit) is logged and returns ``[]``, never an exception that breaks a build. ``client`` is
    injectable for tests; constructing the provider touches no network.
    """

    def __init__(self, *, client: object | None = None) -> None:
        self._client = client

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        try:
            client = self._ensure_client()
            raw = await asyncio.to_thread(lambda: list(client.text(query, max_results=max_results)))
        except Exception:
            logger.warning("duckduckgo_search_failed", query=query, exc_info=True)
            return []
        return _to_results(raw)

    def _ensure_client(self) -> object:
        if self._client is None:
            from ddgs import DDGS

            self._client = DDGS()
        return self._client
