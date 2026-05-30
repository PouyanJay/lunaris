from collections.abc import Sequence

from langchain_core.tools import BaseTool, tool
from lunaris_grounding import Verifier

from ._core import verify_claims_payload


def make_verify_claims_tool(verifier: Verifier) -> BaseTool:
    """A deterministic capability tool: ground factual claims against the corpus.

    The Failure-B moat as a tool. The agent submits claim sentences; the verifier retrieves
    evidence and an independent assessor decides support — each claim comes back SUPPORTED
    (with its citation) or CUT. The publish gate ("no unsupported claim ships") is enforced
    here, not by the model. The verifier is injected (live pgvector + Claude assessor, or stubs).
    """

    @tool
    async def verify_claims(claims: Sequence[str], risk_tier: str = "low") -> dict[str, object]:
        """Ground factual claims against the evidence corpus before publishing.

        ``claims`` is a list of claim sentences. Returns ``{results: [{text, status,
        supportedBy}], citations: [...]}`` where ``status`` is ``supported`` or ``cut``.
        NEVER publish a claim returned as ``cut`` — drop it or revise and re-verify.
        """
        return await verify_claims_payload(verifier, claims, risk_tier)

    return verify_claims
