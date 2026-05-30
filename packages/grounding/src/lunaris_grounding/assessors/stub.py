from lunaris_grounding.evidence import Evidence, Support


class StubSupportAssessor:
    """Deterministic assessor: supports a claim iff evidence exists, using the
    top-scoring evidence's citation. Lets the verifier flow be tested without a model.
    """

    def __init__(self, *, score_when_supported: float = 0.9) -> None:
        self._score = score_when_supported

    async def assess(self, claim_text: str, evidence: list[Evidence]) -> Support:
        if not evidence:
            return Support(score=0.0, citation_id=None)
        best = max(evidence, key=lambda e: e.score)
        return Support(score=self._score, citation_id=best.citation.id)
