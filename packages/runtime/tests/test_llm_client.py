from typing import ClassVar

import langchain_anthropic
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.resilience import build_anthropic_chat_model


class _SpyChatAnthropic:
    """Captures the kwargs ChatAnthropic is constructed with (no network, no real client)."""

    last_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        type(self).last_kwargs = kwargs


def test_builder_injects_the_scoped_tenant_key(monkeypatch) -> None:
    # Arrange — a platform key in env, but a tenant run scope carries the tenant's own key.
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    # Act — build a client inside the tenant scope.
    with run_credentials({"ANTHROPIC_API_KEY": "tenant-key"}):
        build_anthropic_chat_model("claude-haiku-4-5-20251001")

    # Assert — the tenant key is passed explicitly (the platform env key never reaches the client).
    assert _SpyChatAnthropic.last_kwargs["api_key"] == "tenant-key"


def test_builder_uses_env_when_no_scope(monkeypatch) -> None:
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    build_anthropic_chat_model("claude-haiku-4-5-20251001")

    assert _SpyChatAnthropic.last_kwargs["api_key"] == "platform-key"
