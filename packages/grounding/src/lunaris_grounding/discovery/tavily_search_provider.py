import asyncio
import os

import structlog

from .search_result import SearchResult

logger = structlog.get_logger()

_API_KEY_ENV = "SEARCH_API_KEY"


def _to_results(response: object) -> list[SearchResult]:
    # A url-less hit is unfetchable by the extraction layer, so drop it here rather than surface it.
    if not isinstance(response, dict):
        return []
    raw = response.get("results", [])
    if not isinstance(raw, list):
        return []
    results: list[SearchResult] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if url:
            results.append(
                SearchResult(
                    url=url,
                    title=str(item.get("title", "")),
                    snippet=str(item.get("content", "")),
                )
            )
    return results


class TavilySearchProvider:
    """Tavily-backed ``ISearchProvider`` with a lazily-built client (key-gated, best-effort).

    Constructing it touches no network and needs no key; the client (and the ``SEARCH_API_KEY``
    requirement) materialise on the first ``search``. Tavily's client is synchronous, so the call
    runs in a worker thread. Best-effort: any failure — a transport error, or a missing key when the
    composition's key-gate has been bypassed — is logged and returns ``[]``, never an exception that
    breaks a build. ``client`` is injectable for tests.
    """

    def __init__(self, *, api_key_env: str = _API_KEY_ENV, client: object | None = None) -> None:
        self._api_key_env = api_key_env
        self._client = client

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        try:
            client = self._ensure_client()
            response = await asyncio.to_thread(client.search, query, max_results=max_results)
        except Exception:
            logger.warning("tavily_search_failed", query=query, exc_info=True)
            return []
        return _to_results(response)

    def _ensure_client(self) -> object:
        if self._client is None:
            from tavily import TavilyClient

            api_key = os.environ.get(self._api_key_env)
            if not api_key:
                raise RuntimeError(f"{self._api_key_env} is not set; cannot search with Tavily")
            self._client = TavilyClient(api_key=api_key)
        return self._client
