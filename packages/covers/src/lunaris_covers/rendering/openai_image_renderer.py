import base64
from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog
from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.resilience import retry_on_rate_limit

from lunaris_covers.errors import CoverPipelineError

if TYPE_CHECKING:
    from openai import AsyncOpenAI

_logger = structlog.get_logger(__name__)

# The image model + render settings, pinned as constants so they are easy to change in one place.
# GPT Image 2 via the OpenAI Images API at high quality (requirements § Decisions). The size is a
# landscape frame that suits a course card / hero without cropping.
COVER_IMAGE_MODEL = "gpt-image-2"
COVER_IMAGE_SIZE = "1536x1024"
COVER_IMAGE_QUALITY = "high"

# A factory so the client is built per render — picking up the current run's tenant credential scope
# (BYOK), exactly as ``build_chat_model`` resolves the Anthropic key per call. Injectable for tests.
ClientFactory = Callable[[], "AsyncOpenAI"]


def _build_openai_client() -> "AsyncOpenAI":
    """An ``AsyncOpenAI`` on the run's OpenAI key (tenant BYOK scope, else the process env).

    Raises ``CoverPipelineError`` when no key is resolvable — the enqueue tier gate keeps a keyless
    account from ever reaching here, so a missing key is an invariant breach worth surfacing clearly
    rather than a blank-key request the API would reject opaquely.
    """
    from openai import AsyncOpenAI

    api_key = resolve_secret("OPENAI_API_KEY")
    if not api_key:
        raise CoverPipelineError(
            "no OpenAI key in the render scope",
            user_detail="cover generation needs an OpenAI key",
        )
    return AsyncOpenAI(api_key=api_key)


class OpenAiImageRenderer:
    """Renders an art-direction prompt into PNG bytes via the OpenAI Images API (GPT Image 2).

    Builds its client per render through ``client_factory`` so the tenant's BYOK key is picked up
    from the active run scope. GPT Image 2 returns base64 PNG data (no hosted URL), so the bytes are
    decoded here and handed straight to the worker's upload. Any provider error — auth, quota, a
    content-policy refusal — is wrapped as a ``CoverPipelineError`` so the worker settles the job
    FAILED with an owner-safe reason and the full error stays in the logs.
    """

    def __init__(
        self,
        *,
        client_factory: ClientFactory = _build_openai_client,
        model: str = COVER_IMAGE_MODEL,
        size: str = COVER_IMAGE_SIZE,
        quality: str = COVER_IMAGE_QUALITY,
    ) -> None:
        self._client_factory = client_factory
        self._model = model
        self._size = size
        self._quality = quality

    @property
    def model(self) -> str:
        return self._model

    async def render(self, prompt: str) -> bytes:
        from openai import OpenAIError

        client = self._client_factory()
        try:
            # A transient 429/503 is retried in place (the shared, provider-agnostic backoff — it
            # matches openai.RateLimitError too) rather than burning a whole render → QA round and
            # the Claude calls already spent on it. A non-transient error still surfaces below.
            response = await retry_on_rate_limit(
                lambda: client.images.generate(
                    model=self._model, prompt=prompt, size=self._size, quality=self._quality, n=1
                )
            )
        except OpenAIError as exc:
            raise CoverPipelineError(
                f"OpenAI image render failed: {type(exc).__name__}",
                user_detail="the image provider could not render this cover",
            ) from exc
        image = _decode(response)
        _logger.info("cover_renderer.rendered", model=self._model, image_bytes=len(image))
        return image


def _decode(response: object) -> bytes:
    """The PNG bytes from an Images API response, or a ``CoverPipelineError`` on a malformed one.

    GPT Image 2 always returns base64 ``b64_json``; a response missing it (an API/SDK contract
    change, or an empty ``data``) is treated as a render failure rather than an ``AttributeError``
    surfacing raw.
    """
    data = getattr(response, "data", None)
    b64 = getattr(data[0], "b64_json", None) if data else None
    if not b64:
        raise CoverPipelineError(
            "OpenAI image response carried no image data",
            user_detail="the image provider returned no image",
        )
    return base64.b64decode(b64)
