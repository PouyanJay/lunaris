import base64
from collections.abc import Awaitable, Callable

from lunaris_runtime.resilience import build_chat_model, retry_on_rate_limit
from lunaris_runtime.run_config import resolve_config

# Plan/codegen/QA all run on the build's strong, vision-capable tier (plan §8.5: vision floor for
# Gate B). The model is resolved per call so a per-job tenant credential scope (V4) is picked up
# without rebuilding the pipeline; building a ChatAnthropic is cheap and shares the process rate
# limiter.
_DEFAULT_VIDEO_MODEL = "claude-opus-4-8"

# The output ceiling for video text generation. The planner (especially the chaptered overview, a
# multi-chapter contract that is hundreds of JSON lines) and codegen (a whole Manim scene file) emit
# large responses; ChatAnthropic's low default (~1k tokens) truncated the chaptered contract
# mid-JSON (the prod "Invalid JSON: EOF" failure). 16k sits well above the worst-case overview and a
# scene file, and Anthropic bills only generated tokens, so the headroom is free.
VIDEO_MAX_OUTPUT_TOKENS = 16384

TextInvoke = Callable[[str], Awaitable[str]]
VisionInvoke = Callable[[str, list[bytes]], Awaitable[str]]


def default_video_model() -> str:
    """The configured strong model, or the vision-capable default."""
    return resolve_config("LUNARIS_MODEL_STRONG") or _DEFAULT_VIDEO_MODEL


def build_text_invoke(model_id: str, *, max_tokens: int | None = None) -> TextInvoke:
    """A plain text-completion seam over the build chat model (planner + codegen).

    ``max_tokens`` caps each response; the video toolchain passes ``VIDEO_MAX_OUTPUT_TOKENS`` so a
    large structured output (the chaptered overview contract) is not truncated by the provider's
    low default. ``None`` leaves the provider default in place.
    """

    async def invoke(prompt: str) -> str:
        model = build_chat_model(model_id, max_tokens=max_tokens)
        message = await retry_on_rate_limit(lambda: model.ainvoke(prompt))
        return _message_text(message)

    return invoke


def build_vision_invoke(model_id: str) -> VisionInvoke:
    """A multimodal seam: a text prompt plus PNG frames, for Gate B's visual judgement.

    Frames are sent as Anthropic-native base64 image blocks (the build model is keyed → Claude,
    which is vision-capable). ``langchain_core`` is imported lazily so hermetic code never pays
    for it. Unlike the text seam this needs no raised ``max_tokens`` — a QA verdict is a short JSON
    object, so the provider default is ample.
    """

    async def invoke(prompt: str, frames: list[bytes]) -> str:
        from langchain_core.messages import HumanMessage

        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        for frame in frames:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(frame).decode("ascii"),
                    },
                }
            )
        model = build_chat_model(model_id)
        message = await retry_on_rate_limit(lambda: model.ainvoke([HumanMessage(content=content)]))
        return _message_text(message)

    return invoke


def _message_text(message: object) -> str:
    """The text of a chat completion, whether content is a scalar string or a list of blocks.

    Claude usually returns a string, but a multimodal response can be a list of content blocks;
    falling through to ``str(list)`` would feed the parser a Python repr (``[{'type'...``) and
    corrupt every parse-repair turn. So the first text block is extracted explicitly.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text", ""))
            text = getattr(block, "text", None)
            if text is not None:
                return str(text)
    return str(content)
