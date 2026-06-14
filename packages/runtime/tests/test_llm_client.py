from typing import ClassVar

import langchain_anthropic
import pytest
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.resilience import build_chat_model, llm_client, repaired_chat_model


class _SpyChatAnthropic:
    """Captures the kwargs ChatAnthropic is constructed with (no network, no real client)."""

    last_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        type(self).last_kwargs = kwargs


class _SpyChatOpenAI:
    """Captures the kwargs the keyless fallback (RepairingChatOpenAI) is constructed with."""

    last_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        type(self).last_kwargs = kwargs


@pytest.fixture(autouse=True)
def _reset_spies() -> None:
    """Clear the shared capture state so a test can never read kwargs left by an earlier one."""
    _SpyChatAnthropic.last_kwargs = {}
    _SpyChatOpenAI.last_kwargs = {}


def test_builder_injects_the_scoped_tenant_key(monkeypatch) -> None:
    # Arrange — a platform key in env, but a tenant run scope carries the tenant's own key.
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    # Act — build a client inside the tenant scope.
    with run_credentials({"ANTHROPIC_API_KEY": "tenant-key"}):
        build_chat_model("claude-haiku-4-5-20251001")

    # Assert — the tenant key is passed explicitly (the platform env key never reaches the client).
    assert _SpyChatAnthropic.last_kwargs["api_key"] == "tenant-key"


def test_builder_sets_max_tokens_when_given(monkeypatch) -> None:
    # A caller that emits a large response (the video chaptered-overview planner) raises the output
    # ceiling so it is not truncated by ChatAnthropic's low default (the prod EOF failure).
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    build_chat_model("claude-opus-4-8", max_tokens=16384)

    assert _SpyChatAnthropic.last_kwargs["max_tokens"] == 16384


def test_builder_omits_max_tokens_by_default(monkeypatch) -> None:
    # Default behaviour unchanged: no max_tokens forced onto the client (the provider default
    # holds), so every existing caller keeps its current ceiling.
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    build_chat_model("claude-opus-4-8")

    assert "max_tokens" not in _SpyChatAnthropic.last_kwargs


def test_builder_uses_env_when_no_scope(monkeypatch) -> None:
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _SpyChatAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "platform-key")

    build_chat_model("claude-haiku-4-5-20251001")

    assert _SpyChatAnthropic.last_kwargs["api_key"] == "platform-key"


def test_falls_back_to_local_openai_when_no_anthropic_key(monkeypatch) -> None:
    # No Anthropic key anywhere (no scope/env) → the keyless local fallback, not a refused Claude.
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LUNARIS_FALLBACK_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LUNARIS_FALLBACK_LLM_MODEL", raising=False)

    build_chat_model("claude-haiku-4-5-20251001")

    kwargs = _SpyChatOpenAI.last_kwargs
    # Points at a local OpenAI-compatible endpoint with the default Qwen model — and needs no key
    # (a non-secret placeholder, since the local endpoint ignores it).
    assert kwargs["base_url"] == "http://localhost:8080/v1"
    assert kwargs["model"] == "qwen2.5-3b-instruct"
    assert kwargs["api_key"] == "no-key-required"


def test_fallback_honours_env_overrides(monkeypatch) -> None:
    # The model + endpoint are a one-line env swap, so the seam isn't locked to one runtime/model.
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_BASE_URL", "http://gpu-host:9999/v1")
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_MODEL", "qwen2.5-1.5b-instruct")

    build_chat_model("claude-haiku-4-5-20251001")

    kwargs = _SpyChatOpenAI.last_kwargs
    assert kwargs["base_url"] == "http://gpu-host:9999/v1"
    assert kwargs["model"] == "qwen2.5-1.5b-instruct"


def test_keyless_fallback_uses_generous_cpu_timeouts(monkeypatch) -> None:
    # Keyless CPU inference prefills a large agent prompt for minutes before the first token, so the
    # fallback must override langchain_openai's 120s stream-chunk default (and the 60s hosted bound)
    # — else the very first build call is cancelled mid-prefill (observed on prod Qwen-3B on CPU).
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LUNARIS_FALLBACK_LLM_TIMEOUT_S", raising=False)
    monkeypatch.delenv("LUNARIS_FALLBACK_LLM_STREAM_CHUNK_TIMEOUT_S", raising=False)

    build_chat_model("claude-haiku-4-5-20251001")

    kwargs = _SpyChatOpenAI.last_kwargs
    # Pin the documented defaults (far above the 120s stream / 60s request hosted bounds), so an
    # accidental shrink is a regression, not a silently-still-passing >=300 floor.
    assert kwargs["stream_chunk_timeout"] == llm_client._DEFAULT_FALLBACK_STREAM_CHUNK_TIMEOUT_S
    assert kwargs["timeout"] == llm_client._DEFAULT_FALLBACK_REQUEST_TIMEOUT_S


def test_keyless_timeouts_are_env_tunable(monkeypatch) -> None:
    # Operators tune the CPU timeouts per box without a code change (a bigger model / slower host).
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_TIMEOUT_S", "1200")
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_STREAM_CHUNK_TIMEOUT_S", "800")

    build_chat_model("claude-haiku-4-5-20251001")

    kwargs = _SpyChatOpenAI.last_kwargs
    assert kwargs["timeout"] == 1200
    assert kwargs["stream_chunk_timeout"] == 800


def test_keyless_timeouts_fall_back_to_default_on_garbage_env(monkeypatch) -> None:
    # A malformed override must not crash the keyless build — it falls back to the safe default.
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_TIMEOUT_S", "not-a-number")
    monkeypatch.delenv("LUNARIS_FALLBACK_LLM_STREAM_CHUNK_TIMEOUT_S", raising=False)

    build_chat_model("claude-haiku-4-5-20251001")

    kwargs = _SpyChatOpenAI.last_kwargs
    assert kwargs["timeout"] == llm_client._DEFAULT_FALLBACK_REQUEST_TIMEOUT_S
    assert kwargs["stream_chunk_timeout"] == llm_client._DEFAULT_FALLBACK_STREAM_CHUNK_TIMEOUT_S


def test_keyless_model_advertises_its_context_window(monkeypatch) -> None:
    # The keyless model carries a profile so the deep-agent harness summarizes a fraction before it
    # overflows the small local window (deepagents otherwise assumes a 170k window for unknown
    # models and never summarizes inside 16k — the planner then 400s mid-build on context overflow).
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LUNARIS_FALLBACK_LLM_CONTEXT_TOKENS", raising=False)

    build_chat_model("claude-haiku-4-5-20251001")

    profile = _SpyChatOpenAI.last_kwargs["profile"]
    window = llm_client._DEFAULT_FALLBACK_CONTEXT_TOKENS
    # Max *input* = window minus the response reserve, keeping the prompt under the served window.
    assert profile["max_input_tokens"] == window - llm_client._FALLBACK_RESPONSE_RESERVE_TOKENS


def test_keyless_context_window_is_env_tunable(monkeypatch) -> None:
    # Ops match the advertised window to the endpoint's --ctx-size without a code change.
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_CONTEXT_TOKENS", "8192")

    build_chat_model("claude-haiku-4-5-20251001")

    profile = _SpyChatOpenAI.last_kwargs["profile"]
    assert profile["max_input_tokens"] == 8192 - llm_client._FALLBACK_RESPONSE_RESERVE_TOKENS


def test_keyless_context_window_floor_guards_a_tiny_window(monkeypatch) -> None:
    # A misconfigured window smaller than the response reserve can't drive the input budget to
    # zero/negative — the floor holds so deepagents still receives a sane bound.
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_CONTEXT_TOKENS", "1000")  # < the response reserve

    build_chat_model("claude-haiku-4-5-20251001")

    profile = _SpyChatOpenAI.last_kwargs["profile"]
    assert profile["max_input_tokens"] == llm_client._FALLBACK_MIN_INPUT_TOKENS


@pytest.mark.parametrize("bad", ["0", "-30", "inf", "nan"])
def test_keyless_timeouts_reject_nonpositive_or_nonfinite_env(monkeypatch, bad) -> None:
    # A non-positive or non-finite override would wedge the client with a nonsensical bound, so it
    # is rejected in favour of the safe default just like a non-numeric value.
    monkeypatch.setattr(repaired_chat_model, "RepairingChatOpenAI", _SpyChatOpenAI)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LUNARIS_FALLBACK_LLM_TIMEOUT_S", bad)

    build_chat_model("claude-haiku-4-5-20251001")

    assert _SpyChatOpenAI.last_kwargs["timeout"] == llm_client._DEFAULT_FALLBACK_REQUEST_TIMEOUT_S


def test_fallback_model_repairs_tool_calls(monkeypatch) -> None:
    # The keyless fallback is the tool-call-repairing variant (T1b) — a small model's tool-call JSON
    # is its one weak spot, so the safety net is on by construction, not an opt-in agents forget.
    from lunaris_runtime.resilience.repaired_chat_model import RepairingChatOpenAI

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    model = build_chat_model("claude-haiku-4-5-20251001")

    assert isinstance(model, RepairingChatOpenAI)
