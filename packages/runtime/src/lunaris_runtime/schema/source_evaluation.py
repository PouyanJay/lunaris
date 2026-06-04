from .base import CourseModel
from .enums import SourceType, TrustTier


class SourceEvaluation(CourseModel):
    """One discovered source the discovery sub-graph (P6.3) scored and accepted or rejected.

    Carried on a ``SOURCE_EVALUATED`` :class:`AgentEvent` so the live building canvas can render a
    streaming source-vetting table — domain, trust tier, credibility, and the accept/reject verdict
    with a one-line reason — rather than collapsing the decision into a prose beat. Trust tier and
    credibility are populated at acquisition (the P6.2 scorer) and flow untouched to the UI; showing
    them to the *user* is the intended transparency, independent of the in-graph relevance judge,
    which stays blind to source labels.
    """

    kc_id: str
    domain: str
    trust_tier: TrustTier | None = None
    credibility: float | None = None
    source_type: SourceType | None = None
    accepted: bool = False
    reason: str = ""
