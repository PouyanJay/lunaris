from dataclasses import dataclass

from lunaris_runtime.schema import ResourceKind


@dataclass(frozen=True)
class SearchQuery:
    """One planned resource search — the query translator's output (CQ Phase 2).

    A transient domain object (flows inside Python, not over the wire), so a frozen dataclass. The
    translator rewrites a competency into the domain's real search vernacular and emits these:
    ``kind`` routes the query (``VIDEO`` → the ``IVideoSource``, the rest → the shared search),
    ``media_role`` records what the query reaches for (input material / explainer / worked example /
    practice / reference), ``level_hint`` carries the target level baked into the words, and
    ``good_result_looks_like`` is carried to the relevance judge so it scores CONTENT, not the
    title. ``query`` is the only field the search API ever sees — never the raw competency.
    """

    kind: ResourceKind
    query: str
    media_role: str = ""
    level_hint: str = ""
    good_result_looks_like: str = ""
    rationale: str = ""
