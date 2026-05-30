from typing import Any

from lunaris_graph import PrerequisiteGraphBuilder
from lunaris_grounding import Verifier
from mcp.server.fastmcp import FastMCP

from ..harness.tools._core import build_prerequisite_graph_payload, verify_claims_payload


def build_mcp_server(
    builder: PrerequisiteGraphBuilder,
    verifier: Verifier,
    *,
    name: str = "lunaris",
) -> FastMCP:
    """The Lunaris capability registry: the deterministic moats exposed as MCP tools.

    Thin adapters only — business logic stays in ``lunaris_graph`` / ``lunaris_grounding``
    (CLAUDE.md: the MCP server is a registry, not a home for logic). These call the same cores
    as the agent's in-process LangChain tools, so the two surfaces never drift. Capabilities are
    injected, so the live registry serves real Claude/pgvector and tests serve stubs.
    """
    mcp = FastMCP(name)

    @mcp.tool()
    async def build_prerequisite_graph(
        concepts: list[dict[str, Any]],
        goal: str,
        frontier: list[str] | None = None,
    ) -> dict[str, Any]:
        """Order knowledge components into a validated, ACYCLIC prerequisite graph.

        Returns ``{nodes, edges, topoOrder, isAcyclic, ...}``; ``topoOrder`` is the authoritative
        teaching sequence (never teach a concept before its prerequisite).
        """
        return await build_prerequisite_graph_payload(builder, concepts, goal, frontier)

    @mcp.tool()
    async def verify_claims(claims: list[str], risk_tier: str = "low") -> dict[str, Any]:
        """Ground factual claims against the corpus before publishing.

        Each claim returns ``supported`` (with a citation) or ``cut``. Never publish a cut claim.
        """
        return await verify_claims_payload(verifier, claims, risk_tier)

    return mcp
