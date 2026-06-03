from dataclasses import dataclass

from lunaris_runtime.schema import ResourceKind


@dataclass(frozen=True)
class CandidateView:
    """The judge's view of one resource candidate — deliberately WITHOUT the trust tier (P7.4/§15).

    The relevance judge stays blind to our source labels (the trust tier the user later sees), so a
    high-trust label can't rubber-stamp an off-topic resource: it sees only the kind, title, the
    source host, and the URL, and must judge fit from those.
    """

    index: int
    kind: ResourceKind
    title: str
    source: str
    url: str
