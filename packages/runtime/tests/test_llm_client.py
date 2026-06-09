from typing import ClassVar

import langchain_anthropic
import langchain_openai
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.resilience import build_chat_model


class _SpyChatAnthropic:
    """Captures the kwargs ChatAnthropic is constructed with (no network, no real client)."""

    last_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        type(self).last_kwargs = kwargs


class _SpyChatOpenAI:
    """Captures the kwargs the keyless fallback (ChatOpenAI) is constructed with."""

    last_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        type(self).last_kwargs = kwargs


def test_builder_injects_the_scoped_tenant_key(monkeypatch) -> None:
    # Arrange — a platform key in env, but a tenant run scope carries the tenant's own key.
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    # Act — build a client inside the tenant scope.
    with run_credentials({"ANTHROPIC_API_KEY": "tenant-key"}):
        build_chat_model("claude-haiku-4-5-20251001")

    # Assert — the tenant key is passed explicitly (the platform env key never reaches the client).
    assert _SpyChatAnthropic.last_kwargs["api_key"] == "tenant-key"


def test_builder_uses_env_when_no_scope(monkeypatch) -> None:
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    build_chat_model("claude-haiku-4-5-20251001")

    assert _SpyChatAnthropic.last_kwargs["api_key"] == "platform-key"


def test_falls_back_to_local_openai_when_no_anthropic_key(monkeypatch) -> None:
    # No Anthropic key anywhere (no scope/env) → the keyless local fallback, not a refused Claude.
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LUNARIS_FALLBACK_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LUNARIS_FALLBACK_LLM_MODEL", raising=False)

    build_chat_model("claude-haiku-4-5-20251001")

    kwargs = _SpyChatOpenAI.last_kwargs
    # Points at a local OpenAI-compatible endpoint with the default Bonsai model — and needs no key
    # (a non-secret placeholder, since the local endpoint ignores it).
    assert kwargs["base_url"] == "http://localhost:8080/v1"
    assert kwargs["model"] == "bonsai-8b"
    assert kwargs["api_key"] == "no-key-required"


def test_fallback_honours_env_overrides(monkeypatch) -> None:
    # The model + endpoint are a one-line env swap, so the seam isn't locked to one runtime/model.
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_BASE_URL", "http://gpu-host:9999/v1")
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_MODEL", "bonsai-4b")

    build_chat_model("claude-haiku-4-5-20251001")

    kwargs = _SpyChatOpenAI.last_kwargs
    assert kwargs["base_url"] == "http://gpu-host:9999/v1"
    assert kwargs["model"] == "bonsai-4b"
