"""P1b: the claim-verifier moat (Failure-B) as an agent tool. The publish gate — supported
claims keep their citation, unsupported claims are CUT — is enforced by the tool, not the LLM."""

import json
from collections.abc import Callable, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from lunaris_agent.harness import build_course_agent
from lunaris_agent.harness.tools import make_verify_claims_tool
from lunaris_grounding import (
    Evidence,
    StubEvidenceRetriever,
    StubSupportAssessor,
    Verifier,
)
from lunaris_runtime.schema import Citation


def _grounded_verifier() -> Verifier:
    """A verifier whose retriever supplies evidence for any claim mentioning 'binary'."""

    def retrieve(claim: str) -> list[Evidence]:
        if "binary" in claim.lower():
            return [
                Evidence(citation=Citation(id="src::bs", title="CLRS", snippet=claim), score=0.9)
            ]
        return []

    return Verifier(StubEvidenceRetriever(retrieve), StubSupportAssessor())


async def test_verify_tool_supports_grounded_and_cuts_unsupported() -> None:
    # Arrange — one groundable claim, one unsupported.
    tool = make_verify_claims_tool(_grounded_verifier())

    # Act
    result = await tool.ainvoke(
        {"claims": ["Binary search needs sorted input", "The earth is flat"]}
    )

    # Assert — the moat: grounded → supported + citation; unsupported → cut, no citation.
    by_text = {r["text"]: r for r in result["results"]}
    assert by_text["Binary search needs sorted input"]["status"] == "supported"
    assert by_text["Binary search needs sorted input"]["supportedBy"] == "src::bs"
    assert by_text["The earth is flat"]["status"] == "cut"
    assert by_text["The earth is flat"]["supportedBy"] is None
    assert [c["id"] for c in result["citations"]] == ["src::bs"]


async def test_agent_grounds_claims_via_the_verify_tool(
    scripted_model: Callable[[Sequence[BaseMessage]], object],
) -> None:
    # Arrange — the agent submits claims to the deterministic verify tool.
    tool = make_verify_claims_tool(_grounded_verifier())
    model = scripted_model(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "verify_claims",
                        "args": {"claims": ["Binary search needs sorted input"]},
                        "id": "v1",
                    }
                ],
            ),
            AIMessage(content="Verified the claims."),
        ]
    )
    agent = build_course_agent(model, [tool])

    # Act
    result = await agent.ainvoke({"messages": [HumanMessage(content="verify these claims")]})

    # Assert — the tool ran and reported the grounded claim as supported.
    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages
    payload = tool_messages[-1].content
    data = json.loads(payload) if isinstance(payload, str) else payload
    assert data["results"][0]["status"] == "supported"
