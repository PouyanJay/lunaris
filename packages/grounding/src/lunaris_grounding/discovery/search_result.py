from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    """One hit from a web search — the candidate a later step fetches + vets (P7.2 discovery).

    A transient domain object that flows inside Python (not over the wire), so a frozen dataclass,
    not a schema. ``url`` is the only required field; ``title``/``snippet`` are best-effort metadata
    the provider returns for ranking + display.
    """

    url: str
    title: str = ""
    snippet: str = ""
