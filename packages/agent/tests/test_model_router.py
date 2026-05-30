import pytest
from lunaris_agent.models import ModelRouter, ModelTier


class _StubModel:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    async def complete(self, prompt: str) -> str:
        return self._reply


def test_router_returns_model_for_registered_tier() -> None:
    # Arrange
    strong = _StubModel("strong-reply")
    router = ModelRouter({ModelTier.STRONG: strong})

    # Act / Assert
    assert router.for_tier(ModelTier.STRONG) is strong


def test_router_raises_for_unregistered_tier() -> None:
    # Arrange
    router = ModelRouter({ModelTier.STRONG: _StubModel("x")})

    # Act / Assert
    with pytest.raises(KeyError):
        router.for_tier(ModelTier.WORKER)
