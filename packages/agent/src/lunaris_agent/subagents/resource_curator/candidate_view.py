from dataclasses import dataclass

from lunaris_runtime.schema import ResourceKind


@dataclass(frozen=True)
class CandidateView:
    """The judge's view of one resource candidate — deliberately WITHOUT the trust tier (P7.4/§15).

    The relevance judge stays blind to our source labels (the trust tier the user later sees), so a
    high-trust label can't rubber-stamp an off-topic resource. It DOES see the resource's CONTENT —
    the search ``snippet``/description, what a ``good_result_looks_like`` for this query, and the
    target ``level_hint`` — so it can score whether the resource actually teaches the skill at the
    right level rather than guessing from a (possibly clickbait) title (CQ Phase 2 T2).
    """

    index: int
    kind: ResourceKind
    title: str
    source: str
    url: str
    snippet: str = ""
    good_result_looks_like: str = ""
    level_hint: str = ""
