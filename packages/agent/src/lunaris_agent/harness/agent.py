from collections.abc import Callable, Sequence

from deepagents import create_deep_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

COURSE_AGENT_SYSTEM_PROMPT = """You are Lunaris, an agent that builds rigorous, verified courses \
from a single topic and turns them into real learning material.

Plan the build as a todo list, then EXECUTE it by calling tools — never do this work in your head:
- Order concepts only via the prerequisite-graph tool. Teaching a concept before its prerequisite \
is a hard failure; trust the tool's topological order, never your own.
- Ground every factual claim via the claim-verification tool. Never publish a claim the verifier \
did not support — cut it instead.
Assemble the course (concepts, prerequisite graph, curriculum, Merrill lessons), verify it, then \
publish. Keep your reasoning concise and let the tools carry the guarantees."""


def build_course_agent(
    model: str | BaseChatModel,
    tools: Sequence[BaseTool | Callable[..., object]],
    *,
    system_prompt: str = COURSE_AGENT_SYSTEM_PROMPT,
) -> CompiledStateGraph:
    """Compose the Lunaris deep-agent harness: a planning agent over the course-build tools.

    The agent owns planning/reasoning and delegation; the deterministic correctness moats stay
    in their tools (prerequisite ordering, the claim publish gate). ``model`` is a model id for
    the live path (real Claude) or an injected ``BaseChatModel`` — a scripted fake — for the
    deterministic no-key CI path. Returns the compiled LangGraph the API drives and streams.
    """
    return create_deep_agent(model=model, tools=list(tools), system_prompt=system_prompt)
