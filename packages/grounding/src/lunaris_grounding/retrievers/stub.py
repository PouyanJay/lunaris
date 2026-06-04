from collections.abc import Callable

from lunaris_grounding.evidence import Evidence


class StubEvidenceRetriever:
    """Returns evidence from a configurable function of the claim text.

    Lets the verifier be tested without a vector store. The default returns no
    evidence (so every claim would be cut), which is the conservative baseline.
    """

    def __init__(self, fn: Callable[[str], list[Evidence]] | None = None) -> None:
        self._fn = fn or (lambda _claim: [])

    async def retrieve(self, claim_text: str, *, course_id: str | None = None) -> list[Evidence]:
        return self._fn(claim_text)
