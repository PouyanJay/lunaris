import os

from lunaris_graph import PrerequisiteGraphBuilder, StubPrereqJudge
from lunaris_grounding import StubEvidenceRetriever, StubSupportAssessor, Verifier
from mcp.server.fastmcp import FastMCP

from ..composition import build_live_prereq_builder, build_live_verifier
from .server import build_mcp_server


def build_mcp_server_from_env() -> FastMCP:
    """Wire the capability registry from the environment.

    ``LUNARIS_PIPELINE=live`` serves the real capabilities (Claude judge + pgvector/assessor,
    sharing the orchestrator's wiring); otherwise it serves deterministic stubs so ``lunaris-mcp``
    runs offline with no key.
    """
    if os.getenv("LUNARIS_PIPELINE", "stub").lower() == "live":
        return build_mcp_server(build_live_prereq_builder(), build_live_verifier())
    builder = PrerequisiteGraphBuilder(StubPrereqJudge([]))
    verifier = Verifier(StubEvidenceRetriever(), StubSupportAssessor())
    return build_mcp_server(builder, verifier)
