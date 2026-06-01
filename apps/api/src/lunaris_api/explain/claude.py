from lunaris_agent.models.claude import ClaudeModel

from ..schemas.explain import MAX_EXPLAIN_CONTENT, MAX_EXPLAIN_CONTEXT

# Defence in depth: the schema validates at the HTTP boundary, but clip here too so a caller that
# bypasses it (an internal call, a future non-HTTP entrypoint) can't ship an unbounded prompt.
_PROMPT = (
    "You are explaining a piece of data produced during an automated course-build run to a curious "
    "learner watching the build. In 2-4 plain sentences, say what it represents and why it matters "
    "for the course being built. Do not repeat it verbatim, and do not output code or JSON.\n\n"
    "Step context: {context}\n\nData:\n{content}"
)


class ClaudeExplainer:
    """Explains a transcript blob in plain language via Claude (worker tier).

    The client is lazy (built on first ``explain``), so constructing it never needs an API key —
    the route only wires it when a key is reachable.
    """

    def __init__(self, model_name: str) -> None:
        self._model = ClaudeModel(model_name)

    async def explain(self, content: str, context: str | None) -> str:
        prompt = _PROMPT.format(
            context=(context or "(none)")[:MAX_EXPLAIN_CONTEXT],
            content=content[:MAX_EXPLAIN_CONTENT],
        )
        explanation = await self._model.complete(prompt)
        return explanation.strip()
