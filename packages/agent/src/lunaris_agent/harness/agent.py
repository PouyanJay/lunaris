from collections.abc import Callable, Sequence

from deepagents import create_deep_agent
from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

COURSE_AGENT_SYSTEM_PROMPT = """You are Lunaris, an agent that builds rigorous, verified courses \
from a single topic and turns them into real learning material.

Plan the build as a todo list, then EXECUTE it by calling tools and subagents — never do this work \
in your head:
- Order concepts only via the prerequisite-graph tool. Teaching a concept before its prerequisite \
is a hard failure; trust the tool's topological order, never your own.
- After designing the curriculum, delegate lesson authoring to the module-author subagent (the \
`task` tool). It authors every module's Merrill lesson, verifies every factual claim against the \
evidence corpus, and revises until claims are supported — never publishing an unsupported claim.
Assemble the course (concepts, prerequisite graph, curriculum), have the subagent author + verify \
the lessons, then finalize. Keep your reasoning concise and let the tools and the subagent carry \
the guarantees."""


def build_course_agent(
    model: str | BaseChatModel,
    tools: Sequence[BaseTool | Callable[..., object]],
    *,
    subagents: Sequence[SubAgent | CompiledSubAgent] | None = None,
    system_prompt: str = COURSE_AGENT_SYSTEM_PROMPT,
) -> CompiledStateGraph:
    """Compose the Lunaris deep-agent harness: a planning agent over the course-build tools.

    The agent owns planning/reasoning and delegation; the deterministic correctness moats stay
    in their tools (prerequisite ordering, the claim publish gate) and inside the authoring
    subagent's verify→revise loop. ``model`` is a model id for the live path (real Claude) or an
    injected ``BaseChatModel`` — a scripted fake — for the deterministic no-key CI path.
    ``subagents`` registers delegated agents reachable via the ``task`` tool (e.g. the
    module-author loop). Returns the compiled LangGraph the API drives and streams.
    """
    return create_deep_agent(
        model=model,
        tools=list(tools),
        subagents=list(subagents) if subagents else None,
        system_prompt=system_prompt,
    )
