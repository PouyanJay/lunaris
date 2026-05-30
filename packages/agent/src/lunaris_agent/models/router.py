from .protocol import ChatModel
from .tier import ModelTier


class ModelRouter:
    """Routes a request to a model by tier. Swappable per D1 — strong vs worker."""

    def __init__(self, models: dict[ModelTier, ChatModel]) -> None:
        self._models = models

    def for_tier(self, tier: ModelTier) -> ChatModel:
        if tier not in self._models:
            raise KeyError(f"no model registered for tier {tier!r}")
        return self._models[tier]
