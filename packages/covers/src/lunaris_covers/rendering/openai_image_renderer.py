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
        client = self._client_factory()
        return await self._call_images_api(
            lambda: client.images.generate(
                model=self._model, prompt=prompt, size=self._size, quality=self._quality, n=1
            ),
            action="render",
            event="cover_renderer.rendered",
        )

    async def retheme(self, image: bytes, *, instruction: str) -> bytes:
        """Re-theme ``image`` in place via the Images EDIT endpoint (dual-theme light variant).

        An edit of the supplied render under ``instruction`` (the house light-palette instruction),
        so the light twin keeps the dark cover's composition. Shares ``render``'s client/BYOK scope,
        retry, decode and error-wrap path — only the call differs. A provider error is wrapped as
        ``CoverPipelineError`` so the caller can degrade to a dark-only cover rather than failing
        the whole job."""
        client = self._client_factory()
        return await self._call_images_api(
            lambda: client.images.edit(
                model=self._model,
                image=("cover.png", image, "image/png"),
                prompt=instruction,
                size=self._size,
                quality=self._quality,
                n=1,
            ),
            action="re-theme",
            event="cover_renderer.rethemed",
        )

    async def _call_images_api(
        self, call: Callable[[], object], *, action: str, event: str
    ) -> bytes:
        """Run one Images API ``call`` (generate/edit) through the shared retry → decode → wrap.

        ``action`` names the operation in the owner-safe error ("render" / "re-theme"); ``event`` is
        the structlog event on success. A transient 429/503 is retried in place (the shared,
        provider-agnostic backoff — it matches ``openai.RateLimitError`` too) rather than burning
        the Claude calls already spent on the round; any other provider error is wrapped as a
        ``CoverPipelineError`` so the worker settles the job with an owner-safe reason and the full
        error stays in the logs."""
        from openai import OpenAIError

        try:
            response = await retry_on_rate_limit(call)
        except OpenAIError as exc:
            raise CoverPipelineError(
                f"OpenAI image {action} failed: {type(exc).__name__}",
                user_detail=f"the image provider could not {action} this cover",
            ) from exc
        image = _decode(response)
        _logger.info(event, model=self._model, image_bytes=len(image))
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
