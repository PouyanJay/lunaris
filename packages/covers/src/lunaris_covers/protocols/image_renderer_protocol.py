from typing import Protocol


class IImageRenderer(Protocol):
    """Renders an art-direction prompt into raw image bytes (a PNG).

    The default implementation calls the OpenAI Images API (GPT Image 2, high quality) on the job
    owner's BYOK key; the seam keeps the pipeline provider-agnostic and testable against a fake
    client. ``model`` is the image model id, surfaced so the pipeline records it in provenance. A
    render failure raises ``CoverPipelineError``.
    """

    @property
    def model(self) -> str: ...

    async def render(self, prompt: str) -> bytes: ...
