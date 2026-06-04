from pydantic import model_validator

from .base import CourseModel
from .enums import AgentEventKind, ProgressStage
from .source_evaluation import SourceEvaluation


class AgentEvent(CourseModel):
    """One fine-grained event from the deep agent's own execution, streamed live to the UI.

    Where ``ProgressEvent`` marks coarse pipeline *stages*, this is the Claude-grade transcript
    feed: the agent's reasoning text, each tool call (name + args) and its result, and todo/plan
    updates — tapped from the harness's event stream. Ordering is a monotonic ``sequence`` (no
    wall-clock, so the deterministic suite stays stable), and ``run_id`` ties every event back to
    the run for cross-layer correlation. Fields are optional and populated per ``kind``:

    - ``REASONING`` — either ``text`` (a whole thinking beat) OR ``delta`` (one streaming token
      chunk to append to the live beat). The live (real-model) path streams the agent's reasoning
      token-by-token as ``delta`` events; the deterministic path emits whole-message ``text`` beats.
    - ``TOOL_CALL`` — ``tool`` + ``tool_args`` (the call the agent made).
    - ``TOOL_RESULT`` — ``tool`` + ``result`` (a compact summary of what came back).
    - ``TODO`` — ``todos`` (the current plan: each ``{content, status}``).
    - ``SOURCE_EVALUATED`` — ``source`` (one discovered source's domain, trust tier, credibility,
      and accept/reject verdict), so the canvas streams a source-vetting table during discovery.

    ``stage`` is the coarse :class:`ProgressStage` active when the event fired (``None`` for the
    "intro" beats before the first stage), so the live timeline buckets each event under its phase
    deterministically rather than by SSE arrival order.
    """

    kind: AgentEventKind
    run_id: str
    sequence: int = 0
    stage: ProgressStage | None = None
    text: str | None = None
    delta: str | None = None
    tool: str | None = None
    tool_args: dict[str, object] | None = None
    result: str | None = None
    todos: list[dict[str, str]] | None = None
    source: SourceEvaluation | None = None

    @model_validator(mode="after")
    def _text_and_delta_are_exclusive(self) -> "AgentEvent":
        """A REASONING beat is a whole ``text`` or a streaming ``delta``, never both.

        Enforced at the wire boundary so a mis-wired emitter can't ship an ambiguous event.
        """
        if self.text is not None and self.delta is not None:
            raise ValueError("AgentEvent.text and AgentEvent.delta are mutually exclusive")
        return self
