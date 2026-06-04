import re
from typing import Protocol

import structlog

from lunaris_grounding.authorities.scholarly_record import ScholarlyRecord

logger = structlog.get_logger()


class _HttpResponse(Protocol):
    """The slice of an HTTP response this registry uses (httpx.Response satisfies it)."""

    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class _HttpClient(Protocol):
    """The slice of an async HTTP client this registry uses — typed so tests can inject a fake."""

    async def get(self, url: str, *, params: dict[str, str]) -> _HttpResponse: ...


_WORKS_URL = "https://api.openalex.org/works/https://doi.org/"
_TIMEOUT_S = 10.0  # one light GET per uncached source; don't hang a build on a slow response
# A DOI is ``10.<registrant>/<suffix>``; the suffix runs until whitespace or a URL delimiter. Greedy
# on the suffix, then trailing sentence punctuation is trimmed (a DOI lifted from prose/HTML).
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>&?#]+", re.IGNORECASE)
# OpenAlex source types that are NOT peer-reviewed venues: a preprint server is a repository. Plan
# §4a types preprints sub-REPUTABLE, so resolving to one must not floor an open-web source up.
_NON_PEER_REVIEWED_SOURCE_TYPES = frozenset({"repository"})


def _extract_doi(url: str) -> str | None:
    """Pull a DOI out of a URL (a doi.org link or a publisher path embeds one), else ``None``."""
    match = _DOI_RE.search(url)
    if match is None:
        return None
    doi = match.group(0).rstrip(".,);")
    # A real DOI suffix never contains a path-traversal sequence; reject one rather than splice it
    # into the lookup URL (and keep the conservative floor: under-claim on suspicious input).
    if ".." in doi:
        return None
    return doi


def _to_record(payload: object) -> ScholarlyRecord | None:
    """Map an OpenAlex work into a :class:`ScholarlyRecord`, or ``None`` if it isn't peer-reviewed.

    Conservative by design — a trust *floor* should under-claim, not over-trust: a work resolves to
    a record only when OpenAlex reports a venue that is not a preprint repository. A missing/odd
    shape, or a repository-hosted (preprint) source, yields ``None`` so the source stays open web.
    """
    if not isinstance(payload, dict):
        return None
    location = payload.get("primary_location")
    source = location.get("source") if isinstance(location, dict) else None
    if not isinstance(source, dict):
        return None
    source_type = source.get("type")
    if isinstance(source_type, str) and source_type.lower() in _NON_PEER_REVIEWED_SOURCE_TYPES:
        return None
    venue = source.get("display_name")
    citations = payload.get("cited_by_count")
    doi_url = payload.get("doi")
    return ScholarlyRecord(
        venue=venue if isinstance(venue, str) else None,
        doi=_extract_doi(doi_url) if isinstance(doi_url, str) else None,
        citation_count=citations if isinstance(citations, int) else None,
    )


class OpenAlexScholarlyRegistry:
    """Resolves a source URL to its peer-reviewed record via OpenAlex (the live P6.3 registry).

    OpenAlex is keyless and spans every discipline — one integration that answers "is this a real,
    cited paper, and in what venue" without a per-field allowlist. A DOI is extracted from the URL
    (a ``doi.org`` link or a publisher path embeds one) and looked up by id; the optional ``mailto``
    joins OpenAlex's faster "polite pool". Best-effort and off the critical path: a URL with no DOI,
    a preprint, a transport error, an unindexed DOI, or an odd response all resolve to ``None`` —
    never an exception that breaks a build. ``client`` is an injectable async HTTP client for tests.
    """

    def __init__(self, *, mailto: str | None = None, client: _HttpClient | None = None) -> None:
        self._mailto = mailto
        self._client = client

    async def lookup(self, url: str) -> ScholarlyRecord | None:
        doi = _extract_doi(url)
        if doi is None:
            return None
        params = {"mailto": self._mailto} if self._mailto else {}
        try:
            response = await self._get(f"{_WORKS_URL}{doi}", params)
            response.raise_for_status()
            return _to_record(response.json())
        except Exception:
            logger.debug("openalex_lookup_failed", doi=doi, exc_info=True)
            return None

    async def _get(self, url: str, params: dict[str, str]) -> _HttpResponse:
        """Issue the request via the injected client (tests) or a per-call httpx client.

        Isolated so ``httpx`` is imported lazily (no module-load cost) and a fake client can be
        injected without it.
        """
        if self._client is not None:
            return await self._client.get(url, params=params)
        import httpx

        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            return await client.get(url, params=params)
