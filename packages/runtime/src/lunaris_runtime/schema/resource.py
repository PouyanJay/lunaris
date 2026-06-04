from .base import CourseModel
from .enums import ResourceKind, TrustTier


class Resource(CourseModel):
    """One vetted external learning resource attached to a lesson phase (P7.4 — the "go beyond").

    A suggested aid the curator found, scored, and attached to the most relevant Merrill phase —
    never a replacement for the verified lesson. Structural provenance: ``url`` + ``source`` (the
    host) + ``fetched_at`` + ``trust_tier`` are constructed where the candidate is acquired and flow
    untouched to the reader, so a learner can audit where a resource came from and why.
    The LLM relevance judge is kept blind to ``trust_tier`` (the user sees the badge, the judge does
    not), so a high-trust label can't rubber-stamp an off-topic resource.
    """

    kind: ResourceKind
    title: str
    url: str
    source: str = ""  # the host/domain shown to the learner (e.g. "youtube.com")
    why: str = ""  # one line: why this resource helps with the lesson's competency
    trust_tier: TrustTier = TrustTier.OPEN
    credibility: float = 0.0  # 0..1 blended quality score (CRAAP + level-match + cross-signals)
    fetched_at: str = ""  # ISO-8601 instant, stamped at acquisition
    duration: str | None = None  # for video — human-readable runtime (e.g. "12:01")
    author: str | None = None  # the channel/author when the source exposes it
