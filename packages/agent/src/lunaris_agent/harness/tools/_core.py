"""Shared capability implementations behind the agent's tools.

Each function is the single source of truth for one capability's adapter logic, so the
LangChain ``@tool`` (in-process, what the agent calls) and the MCP tool (the external
capability registry) stay byte-identical — neither holds business logic, both call here.
"""

from collections.abc import Mapping, Sequence

from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_grounding import Verifier
from lunaris_runtime.schema import BloomLevel, Claim, KnowledgeComponent, RiskTier


async def build_prerequisite_graph_payload(
    builder: PrerequisiteGraphBuilder,
    concepts: Sequence[Mapping[str, object]],
    goal: str,
    frontier: Sequence[str] | None = None,
) -> dict[str, object]:
    """Order proposed concepts into a validated, acyclic prerequisite graph (Failure-A moat)."""
    kcs = [
        KnowledgeComponent(
            id=str(concept["id"]),
            label=str(concept.get("label", concept["id"])),
            definition=str(concept.get("definition", "")),
            difficulty=float(concept.get("difficulty", 0.5)),  # type: ignore[arg-type]
            bloom_ceiling=BloomLevel.APPLY,
        )
        for concept in concepts
    ]
    graph = await builder.build(kcs, frontier=list(frontier or []), goal=goal)
    return graph.model_dump(by_alias=True)


async def verify_claims_payload(
    verifier: Verifier,
    claims: Sequence[str],
    risk_tier: str = "low",
) -> dict[str, object]:
    """Ground claims against the corpus; enforce the supported-or-cut publish gate (Failure-B)."""
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
