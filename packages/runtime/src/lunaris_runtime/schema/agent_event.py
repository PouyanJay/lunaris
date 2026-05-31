from .base import CourseModel
from .enums import AgentEventKind


class AgentEvent(CourseModel):
    """One fine-grained event from the deep agent's own execution, streamed live to the UI.

    Where ``ProgressEvent`` marks coarse pipeline *stages*, this is the Claude-grade transcript
    feed: the agent's reasoning text, each tool call (name + args) and its result, and todo/plan
    updates — tapped from the harness's event stream. Ordering is a monotonic ``sequence`` (no
    wall-clock, so the deterministic suite stays stable), and ``run_id`` ties every event back to
    the run for cross-layer correlation. Fields are optional and populated per ``kind``:

    - ``REASONING`` — ``text`` carries a chunk of the agent's thinking.
    - ``TOOL_CALL`` — ``tool`` + ``tool_args`` (the call the agent made).
    - ``TOOL_RESULT`` — ``tool`` + ``result`` (a compact summary of what came back).
    - ``TODO`` — ``todos`` (the current plan: each ``{content, status}``).
    """

    kind: AgentEventKind
    run_id: str
    sequence: int = 0
    text: str | None = None
    tool: str | None = None
    tool_args: dict[str, object] | None = None
    result: str | None = None
    todos: list[dict[str, str]] | None = None
