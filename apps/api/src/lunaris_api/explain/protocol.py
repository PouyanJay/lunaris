from typing import Protocol


class IExplainer(Protocol):
    """Explains a transcript blob (JSON/code/data) in plain language for a watching learner."""

    async def explain(self, content: str, context: str | None) -> str: ...
