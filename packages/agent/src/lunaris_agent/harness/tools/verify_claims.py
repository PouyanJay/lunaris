from collections.abc import Sequence

from langchain_core.tools import BaseTool, tool
from lunaris_grounding import Verifier
from lunaris_runtime.schema import Claim, RiskTier


def make_verify_claims_tool(verifier: Verifier) -> BaseTool:
    """A deterministic capability tool: ground factual claims against the corpus.

    The Failure-B moat as a tool. The agent submits claim sentences; the verifier retrieves
    evidence and an independent assessor decides support — each claim comes back SUPPORTED
    (with its citation) or CUT. The publish gate ("no unsupported claim ships") is enforced
    here, not by the model: the agent must drop anything returned as cut. The verifier is
    injected, so the live path uses pgvector + the Claude assessor and the no-key path uses stubs.
    """

    @tool
    async def verify_claims(claims: Sequence[str], risk_tier: str = "low") -> dict[str, object]:
        """Ground factual claims against the evidence corpus before publishing.

        ``claims`` is a list of claim sentences. Returns ``{results: [{text, status,
        supportedBy}], citations: [...]}`` where ``status`` is ``supported`` or ``cut``.
        NEVER publish a claim returned as ``cut`` — drop it or revise and re-verify.
        """
        claim_objects = [Claim(text=text) for text in claims]
        tier = RiskTier.HIGH if risk_tier == "high" else RiskTier.LOW
        citations = await verifier.verify(claim_objects, risk_tier=tier)
        return {
            "results": [
                {
                    "text": claim.text,
                    "status": claim.verifier_status.value,
                    "supportedBy": claim.supported_by,
                }
                for claim in claim_objects
            ],
            "citations": [citation.model_dump(by_alias=True) for citation in citations],
        }

    return verify_claims
