"""OpenAiImageRenderer contract (course-cover-images T4): the GPT Image 2 seam.

The renderer is exercised against a fake ``AsyncOpenAI`` (never a live call): a successful render
decodes base64 to PNG bytes and asks the model at high quality; any provider error, or a malformed
response, is wrapped as a ``CoverPipelineError`` so the worker settles the job FAILED with an
owner-safe reason instead of leaking a raw provider exception.
"""

import base64

import pytest
from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.rendering.openai_image_renderer import OpenAiImageRenderer
from openai import OpenAIError

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _Images:
    def __init__(self, *, png: bytes | None = _PNG, raises: Exception | None = None) -> None:
        self._png = png
        self._raises = raises
        self.kwargs: dict[str, object] = {}
        self.edit_kwargs: dict[str, object] = {}

    async def generate(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        if self._raises is not None:
            raise self._raises
        b64 = base64.b64encode(self._png).decode("ascii") if self._png is not None else None
        return type("Resp", (), {"data": [type("Datum", (), {"b64_json": b64})()]})()

    async def edit(self, **kwargs: object) -> object:
        self.edit_kwargs = kwargs
        if self._raises is not None:
            raise self._raises
        # A distinct image so a test can tell the re-theme output from the input render.
        light = (self._png + b"L") if self._png is not None else None
        b64 = base64.b64encode(light).decode("ascii") if light is not None else None
        return type("Resp", (), {"data": [type("Datum", (), {"b64_json": b64})()]})()


class _FakeClient:
    def __init__(self, images: _Images) -> None:
        self.images = images


@pytest.mark.asyncio
async def test_render_decodes_base64_png_and_asks_at_high_quality() -> None:
    images = _Images()
    renderer = OpenAiImageRenderer(client_factory=lambda: _FakeClient(images))

    result = await renderer.render("a lone amber lighthouse")

    assert result == _PNG
    assert images.kwargs["model"] == "gpt-image-2"
    assert images.kwargs["prompt"] == "a lone amber lighthouse"
    assert images.kwargs["quality"] == "high"
    assert images.kwargs["size"] == "1536x1024"
    assert renderer.model == "gpt-image-2"


@pytest.mark.asyncio
async def test_provider_error_is_wrapped_as_cover_pipeline_error() -> None:
    images = _Images(raises=OpenAIError("quota exceeded"))
    renderer = OpenAiImageRenderer(client_factory=lambda: _FakeClient(images))

    with pytest.raises(CoverPipelineError) as caught:
        await renderer.render("prompt")
    # The owner-safe detail is surfaced; the raw provider message stays out of the job row.
    assert caught.value.user_detail
    assert "quota exceeded" not in str(caught.value.user_detail)


@pytest.mark.asyncio
async def test_response_without_image_data_is_a_pipeline_error() -> None:
    images = _Images(png=None)  # a response whose datum carries no b64_json
    renderer = OpenAiImageRenderer(client_factory=lambda: _FakeClient(images))

    with pytest.raises(CoverPipelineError):
        await renderer.render("prompt")


@pytest.mark.asyncio
async def test_retheme_edits_the_given_image_under_the_instruction() -> None:
    images = _Images()
    renderer = OpenAiImageRenderer(client_factory=lambda: _FakeClient(images))

    light = await renderer.retheme(_PNG, instruction="make it light")

    assert light == _PNG + b"L"  # the edited (light) image, distinct from the input render
    assert images.edit_kwargs["model"] == "gpt-image-2"
    assert images.edit_kwargs["prompt"] == "make it light"
    assert images.edit_kwargs["size"] == "1536x1024"
    # The dark render is handed to the edit endpoint as the image to re-theme.
    assert images.edit_kwargs["image"] == ("cover.png", _PNG, "image/png")


@pytest.mark.asyncio
async def test_retheme_provider_error_is_wrapped_as_cover_pipeline_error() -> None:
    images = _Images(raises=OpenAIError("content policy"))
    renderer = OpenAiImageRenderer(client_factory=lambda: _FakeClient(images))

    with pytest.raises(CoverPipelineError) as caught:
        await renderer.retheme(_PNG, instruction="make it light")
    assert caught.value.user_detail
    assert "content policy" not in str(caught.value.user_detail)
