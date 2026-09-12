from contextlib import nullcontext

from lunaris_runtime.metering.cost_scope import CostScope, cost_scope, current_cost_scope
from lunaris_runtime.resilience import build_chat_model

from .models.completion import SimCompletion


class ClaudeSimModel:
    """One metered model call; orchestration owns retries and total budgets."""

    def __init__(self, model_name: str) -> None:
        self._name = model_name

    @property
    def model_name(self) -> str:
        return self._name

    async def complete(
        self, prompt: str, *, max_tokens: int, images: list[str] | None = None
    ) -> SimCompletion:
        client = build_chat_model(self._name, max_tokens=max_tokens, component="live.sim.factory")
        if not hasattr(client, "max_retries"):
            raise ValueError("This provider does not support bounded simulator generation.")
        client.max_retries = 0
        parent = current_cost_scope()
        scope = self._scope(parent)
        try:
            with cost_scope(scope) if scope else nullcontext():
                message = await client.bind(max_tokens=max_tokens).ainvoke(
                    self._message(prompt, images)
                )
        finally:
            if parent and scope:
                parent.entries.extend(scope.entries)
        if not isinstance(message.content, str):
            raise ValueError("The simulator model did not return text.")
        usage = message.usage_metadata or {}
        actual_model = getattr(client, "model", None) or getattr(client, "model_name", None)
        return SimCompletion(
            text=message.content,
            model=str(actual_model or type(client).__name__),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=sum(entry.amount for entry in scope.entries) if scope else None,
        )

    def _scope(self, parent: CostScope | None) -> CostScope | None:
        if parent is None:
            return None
        return CostScope(
            run_id=parent.run_id,
            subject_type=parent.subject_type,
            subject_id=parent.subject_id,
            owner_id=parent.owner_id,
            price_book=parent.price_book,
            currency=parent.currency,
        )

    def _message(self, prompt: str, images: list[str] | None) -> str | list[dict]:
        if not images:
            return prompt
        content = [{"type": "text", "text": prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}}
            for image in images
        )
        return [{"role": "user", "content": content}]
