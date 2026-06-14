"""Model-adapter wiring: the video text seam carries a generous output ceiling so a large
structured output (the chaptered overview contract) is not truncated by the provider default (the
prod "Invalid JSON: EOF" failure). The chat model itself is stubbed — no network, no key."""

from pathlib import Path

from lunaris_video.pipeline import factory, model_adapters
from lunaris_video.pipeline.model_adapters import VIDEO_MAX_OUTPUT_TOKENS, build_text_invoke


class _StubModel:
    async def ainvoke(self, prompt: object) -> str:
        return "ok"


async def test_text_invoke_requests_the_configured_max_tokens(monkeypatch) -> None:
    # Arrange — capture the max_tokens the seam asks build_chat_model for, without a real client.
    captured: dict[str, object] = {}

    def _fake_build(model_id: str, *, max_tokens: int | None = None) -> _StubModel:
        captured["model_id"] = model_id
        captured["max_tokens"] = max_tokens
        return _StubModel()

    monkeypatch.setattr(model_adapters, "build_chat_model", _fake_build)
    invoke = build_text_invoke("claude-opus-4-8", max_tokens=VIDEO_MAX_OUTPUT_TOKENS)

    # Act
    result = await invoke("plan this overview")

    # Assert — the ceiling is threaded to the chat model, and the completion text is returned.
    assert captured["max_tokens"] == VIDEO_MAX_OUTPUT_TOKENS
    assert result == "ok"


def test_video_max_output_tokens_is_generous_enough_for_a_chaptered_contract() -> None:
    # A chaptered overview contract is hundreds of JSON lines; the ceiling must sit well above it
    # (and a scene file) so a big response is never truncated. Guard against an accidental shrink.
    assert VIDEO_MAX_OUTPUT_TOKENS >= 8192


def test_factory_wires_the_text_invoke_with_the_raised_ceiling(monkeypatch, tmp_path: Path) -> None:
    # Arrange — the worker's real pipeline must build its planner/codegen seam with the raised
    # ceiling, not the provider default (else the overview planner truncates on prod).
    captured: dict[str, object] = {}

    def _spy_text_invoke(model_id: str, *, max_tokens: int | None = None):
        captured["max_tokens"] = max_tokens
        return lambda prompt: prompt

    monkeypatch.setattr(factory, "build_text_invoke", _spy_text_invoke)
    monkeypatch.setattr(factory, "build_vision_invoke", lambda model_id: lambda prompt, frames: "")

    # Act — build the toolchain (a store double isn't needed; the maker wires the seams up front).
    factory.build_video_pipeline(store=object(), workspace_root=tmp_path)

    # Assert — the text seam was wired with the video output ceiling.
    assert captured["max_tokens"] == VIDEO_MAX_OUTPUT_TOKENS
