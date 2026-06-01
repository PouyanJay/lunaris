from pydantic import Field

from .base import CamelModel

# The trust-boundary caps for a single Explain call — the one authoritative source for these bounds
# (the prompt builder in ClaudeExplainer clips to the same values, defence-in-depth).
MAX_EXPLAIN_CONTENT = 8000
MAX_EXPLAIN_CONTEXT = 400


class ExplainRequest(CamelModel):
    """A blob from the build transcript to explain in plain language. Bounded so a request can't
    ship an unbounded prompt to the model (cost + abuse)."""

    content: str = Field(min_length=1, max_length=MAX_EXPLAIN_CONTENT)
    context: str | None = Field(default=None, max_length=MAX_EXPLAIN_CONTEXT)


class ExplainResponse(CamelModel):
    """The plain-language explanation of a blob."""

    explanation: str
