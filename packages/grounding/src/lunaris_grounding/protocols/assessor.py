from typing import Protocol

from lunaris_grounding.evidence import Evidence, Support


class ISupportAssessor(Protocol):
    """Judges whether retrieved evidence supports a claim.

    MUST be independent of the author (a different model or a fresh adversarial
    context) so it doesn't share the author's blind spots — this separation is the
    cheapest large quality win in the system (build-spec §08).
    """

    async def assess(self, claim_text: str, evidence: list[Evidence]) -> Support: ...
