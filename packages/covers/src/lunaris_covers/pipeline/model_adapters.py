from lunaris_runtime.resilience import build_chat_model, retry_on_rate_limit
from lunaris_runtime.run_config import resolve_config

from lunaris_covers.art_direction.cover_art_director import TextInvoke

# The art director + vision QA run on the build's strong, vision-capable tier — the same Claude the
# video pipeline uses for planning/QA. Resolved per call so a per-job tenant credential scope (BYOK)
# is picked up without rebuilding the pipeline; building a ChatAnthropic is cheap and all live
# Claude calls share the process rate limiter.
_DEFAULT_COVER_MODEL = "claude-opus-4-8"

# The art director writes a short image prompt (2-4 sentences); the provider default output ceiling
# is ample, so — unlike the video planner — no raised max_tokens is needed.


def cover_claude_model() -> str:
    """The configured strong model, or the vision-capable default the covers pipeline runs on."""
    return resolve_config("LUNARIS_MODEL_STRONG") or _DEFAULT_COVER_MODEL


def build_cover_text_invoke(model_id: str) -> TextInvoke:
    """A plain text-completion seam over the build chat model — the art director's Claude seam.

    Resolves + hardens the model per call (timeout, bounded retries, the shared rate limiter) and
    absorbs a transient 429 via ``retry_on_rate_limit``. The BYOK key is resolved inside
    ``build_chat_model`` from the active run scope, so the call authenticates as the job's tenant.
    """

    async def invoke(prompt: str) -> str:
        model = build_chat_model(model_id)
        message = await retry_on_rate_limit(lambda: model.ainvoke(prompt))
        return _message_text(message)

    return invoke


def _message_text(message: object) -> str:
    """The text of a chat completion, whether content is a scalar string or a list of blocks.

    Claude usually returns a string, but a multimodal-capable model can return a list of content
    blocks; falling through to ``str(list)`` would feed a Python repr downstream, so the first text
    block is extracted explicitly. Mirrors ``lunaris_video``'s adapter.
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
